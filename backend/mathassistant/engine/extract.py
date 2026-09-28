"""Image -> problem text (spec §4, Phase 2).

One vision call per image. The model transcribes every separate problem it
can see (up to MAX_PROBLEMS, in reading order): math as LaTeX, word problems as
plain text. It never solves. The learner picks one to start with and confirms
or edits it; the others can be saved to "Up next" (no AI cost until started).

Images are held in memory for this one call only: never written to disk,
the database, or the logs.
"""

from __future__ import annotations

import base64
import binascii
import logging
from dataclasses import dataclass, field

from ..providers.base import LLMProvider, StructuredRequest, Usage

log = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 5 * 1024 * 1024        # after base64 decode; the client downscales well below this
MAX_PROBLEMS = 20                        # per image
EXTRACT_MAX_TOKENS = 3000                # a full worksheet page can list many problems

# Media types the Anthropic API accepts, with their file signatures.
_SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/webp": (b"RIFF",),             # + "WEBP" at offset 8, checked below
    "image/gif": (b"GIF87a", b"GIF89a"),
}

EXTRACT_SYSTEM = """\
You read math problems from an image for a tutoring program. You are a transcriber, not a solver.

- List EVERY separate problem you can see, in reading order (at most 20). If there is only one, list one.
- Copy each problem exactly as written. Do NOT solve anything, simplify, or add answers, even if answers or worked steps appear in the image (leave those out).
- label: the problem's printed number or letter ("3", "4b"), or "" if none.
- If a problem is mostly symbols/equations: kind="math", latex = LaTeX without $ delimiters (e.g. "\\frac{d}{dx}\\sin(x^2)" or "2x+3=7"). Put short instruction words ("Solve", "Simplify") in instruction.
- If it is a word problem (sentences): kind="words", text = the full text, with any math written as plain text (e.g. "3x + 5").
- Shared directions for a group ("Solve each equation") go in each problem's instruction.
- Skip headers, names, dates, and page numbers.
- If you can't read any problem, set readable=false, problems=[], and explain briefly in note (e.g. "too blurry", "no math problem").
"""

_PROBLEM_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "kind": {"type": "string", "enum": ["math", "words"]},
        "latex": {"type": "string"},
        "text": {"type": "string"},
        "instruction": {"type": "string"},
    },
    "required": ["label", "kind", "latex", "text", "instruction"],
    "additionalProperties": False,
}

EXTRACT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "readable": {"type": "boolean"},
        "problems": {"type": "array", "items": _PROBLEM_SCHEMA},
        "note": {"type": "string"},
    },
    "required": ["readable", "problems", "note"],
    "additionalProperties": False,
}


class ImageError(ValueError):
    """Bad image input (type, size, or content doesn't match its type)."""


@dataclass
class ExtractedProblem:
    label: str
    kind: str            # "math" | "words"
    latex: str
    text: str
    instruction: str

    def to_dict(self) -> dict:
        return {"label": self.label, "kind": self.kind, "latex": self.latex, "text": self.text,
                "instruction": self.instruction}


@dataclass
class Extraction:
    readable: bool
    note: str
    usage: Usage
    problems: list[ExtractedProblem] = field(default_factory=list)


def decode_image(image_base64: str, media_type: str) -> bytes:
    """Validate and decode an uploaded image. Raises ImageError."""
    if media_type not in _SIGNATURES:
        raise ImageError("Use a PNG, JPEG, WebP, or GIF image.")
    data = image_base64.split(",", 1)[1] if image_base64.startswith("data:") else image_base64
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise ImageError("That image couldn't be read.") from None
    if not raw:
        raise ImageError("That image is empty.")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ImageError("That image is too large. Crop it to just the problems.")
    if not any(raw.startswith(sig) for sig in _SIGNATURES[media_type]):
        raise ImageError("That file isn't the image type it claims to be.")
    if media_type == "image/webp" and raw[8:12] != b"WEBP":
        raise ImageError("That file isn't the image type it claims to be.")
    return raw


def _clean_problem(raw: object) -> ExtractedProblem | None:
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind") if raw.get("kind") in ("math", "words") else "math"
    p = ExtractedProblem(
        label=str(raw.get("label", "") or "").strip()[:12],
        kind=kind,
        latex=str(raw.get("latex", "") or "").strip()[:2000],
        text=str(raw.get("text", "") or "").strip()[:2000],
        instruction=str(raw.get("instruction", "") or "").strip()[:200],
    )
    # A math problem the model wrote as text (or vice versa) is still usable.
    if kind == "math" and not p.latex and p.text:
        p.kind = "words"
    if kind == "words" and not p.text and p.latex:
        p.kind = "math"
    if not (p.latex if p.kind == "math" else p.text):
        return None
    return p


def extract_problems(provider: LLMProvider, image: bytes, media_type: str) -> Extraction:
    """One vision call. The image bytes are not retained after this returns."""
    b64 = base64.standard_b64encode(image).decode("ascii")
    req = StructuredRequest(
        system_blocks=[EXTRACT_SYSTEM],
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
            {"type": "text", "text": "Transcribe the math problems in this image."},
        ]}],
        schema=EXTRACT_SCHEMA,
        max_tokens=EXTRACT_MAX_TOKENS,
        purpose="vision",
    )
    result = provider.structured(req)
    d = result.data or {}
    raw_list = d.get("problems") if isinstance(d.get("problems"), list) else []
    problems = [p for p in (_clean_problem(r) for r in raw_list[:MAX_PROBLEMS]) if p]
    ex = Extraction(
        readable=bool(d.get("readable")) and not result.malformed and bool(problems),
        note=str(d.get("note", "") or "").strip()[:200],
        usage=result.usage,
        problems=problems,
    )
    if not ex.readable and not ex.note:
        ex.note = "no problem found"
    log.info("vision extraction: readable=%s problems=%d", ex.readable, len(ex.problems))  # never the content
    return ex
