"""Image -> problem text (spec §4, Phase 2).

One vision call per image. The model transcribes the single problem in the
(already cropped and downscaled) image: math as LaTeX, a word problem as
plain text. It never solves. The result goes back to the learner to confirm
or edit; tutoring (the intake call) starts only after they press Start.

Images are held in memory for this one call only: never written to disk,
the database, or the logs.
"""

from __future__ import annotations

import base64
import binascii
import logging
from dataclasses import dataclass

from ..providers.base import LLMProvider, StructuredRequest, Usage

log = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 5 * 1024 * 1024        # after base64 decode; the client downscales well below this
EXTRACT_MAX_TOKENS = 800

# Media types the Anthropic API accepts, with their file signatures.
_SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/webp": (b"RIFF",),             # + "WEBP" at offset 8, checked below
    "image/gif": (b"GIF87a", b"GIF89a"),
}

EXTRACT_SYSTEM = """\
You read ONE math problem from an image for a tutoring program. You are a transcriber, not a solver.

- Copy the problem exactly as written. Do NOT solve it, simplify it, or add an answer, even if an answer or worked steps appear in the image (leave those out).
- If it is mostly symbols/equations, set kind="math" and put it in latex (LaTeX without $ delimiters), e.g. "\\frac{d}{dx}\\sin(x^2)" or "2x+3=7". Put any short instruction words ("Solve", "Simplify") in instruction.
- If it is a word problem (sentences), set kind="words" and put the full text in text. Write any math inside it as plain text (e.g. "3x + 5").
- If several problems are visible, transcribe only the most complete one near the center and set note to "several problems".
- If you can't read a problem, set readable=false and explain briefly in note (e.g. "too blurry", "no math problem").
"""

EXTRACT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "readable": {"type": "boolean"},
        "kind": {"type": "string", "enum": ["math", "words"]},
        "latex": {"type": "string"},
        "text": {"type": "string"},
        "instruction": {"type": "string"},
        "note": {"type": "string"},
    },
    "required": ["readable", "kind", "latex", "text", "instruction", "note"],
    "additionalProperties": False,
}


class ImageError(ValueError):
    """Bad image input (type, size, or content doesn't match its type)."""


@dataclass
class Extraction:
    readable: bool
    kind: str            # "math" | "words"
    latex: str
    text: str
    instruction: str
    note: str
    usage: Usage


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
        raise ImageError("That image is too large. Crop it to just the problem.")
    if not any(raw.startswith(sig) for sig in _SIGNATURES[media_type]):
        raise ImageError("That file isn't the image type it claims to be.")
    if media_type == "image/webp" and raw[8:12] != b"WEBP":
        raise ImageError("That file isn't the image type it claims to be.")
    return raw


def extract_problem(provider: LLMProvider, image: bytes, media_type: str) -> Extraction:
    """One vision call. The image bytes are not retained after this returns."""
    b64 = base64.standard_b64encode(image).decode("ascii")
    req = StructuredRequest(
        system_blocks=[EXTRACT_SYSTEM],
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
            {"type": "text", "text": "Transcribe the math problem in this image."},
        ]}],
        schema=EXTRACT_SCHEMA,
        max_tokens=EXTRACT_MAX_TOKENS,
        purpose="vision",
    )
    result = provider.structured(req)
    d = result.data or {}
    kind = d.get("kind") if d.get("kind") in ("math", "words") else "math"
    ex = Extraction(
        readable=bool(d.get("readable")) and not result.malformed,
        kind=kind,
        latex=str(d.get("latex", "") or "").strip()[:2000],
        text=str(d.get("text", "") or "").strip()[:2000],
        instruction=str(d.get("instruction", "") or "").strip()[:200],
        note=str(d.get("note", "") or "").strip()[:200],
        usage=result.usage,
    )
    if ex.readable and not (ex.latex if kind == "math" else ex.text):
        ex.readable = False
        ex.note = ex.note or "no problem found"
    log.info("vision extraction: readable=%s kind=%s", ex.readable, ex.kind)  # never the content
    return ex
