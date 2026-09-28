"""Display box payloads: schema validation, gating, wiping (spec §9).

Phase 1 types:
* `latex` — tutor-supplied expressions / parallel examples (from the AI turn call).
* `steps` — the step checklist, rendered locally from engine state (never from the AI).

Malformed or unknown payloads are logged and dropped: the box stays empty,
nothing crashes.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

log = logging.getLogger(__name__)

MAX_ITEMS = 4
MAX_LATEX_CHARS = 300
MAX_CAPTION_CHARS = 140

# "When the learner asks to see an example" (§9.1).
_EXAMPLE_REQUEST_RE = re.compile(r"\b(example|show me|can you show|draw|picture|visual)\b", re.I)


class LatexItem(BaseModel):
    latex: str = Field(min_length=1, max_length=MAX_LATEX_CHARS)
    caption: str = Field(default="", max_length=MAX_CAPTION_CHARS)

    @field_validator("latex")
    @classmethod
    def _no_html(cls, v: str) -> str:
        # KaTeX renders with trust=false on the client, but reject obvious junk early.
        if "<" in v and "script" in v.lower():
            raise ValueError("html not allowed")
        return v


class LatexPayload(BaseModel):
    type: str
    title: str = Field(default="", max_length=80)
    items: list[LatexItem] = Field(min_length=1, max_length=MAX_ITEMS)

    @field_validator("type")
    @classmethod
    def _type_is_latex(cls, v: str) -> str:
        if v != "latex":
            raise ValueError("unsupported display type")
        return v


def validate_payload(raw: Any) -> dict | None:
    """Return a clean payload dict, or None (box stays empty) if invalid/unknown."""
    if raw in (None, {}, []):
        return None
    if not isinstance(raw, dict):
        log.warning("display payload dropped: not an object")
        return None
    ptype = raw.get("type")
    if ptype != "latex":
        # `steps` is local-only; `graph`/`diagram` are Phase 4.
        log.warning("display payload dropped: type %r not allowed from the model", ptype)
        return None
    try:
        return LatexPayload.model_validate(raw).model_dump()
    except ValidationError as exc:
        log.warning("display payload dropped: %d validation errors", len(exc.errors()))
        return None


def payload_texts(payload: dict | None) -> list[str]:
    """All strings in a payload (for the leak guard)."""
    if not payload:
        return []
    out = [payload.get("title", "")]
    for it in payload.get("items", []):
        out.append(f"${it.get('latex', '')}$")
        out.append(it.get("caption", ""))
    return [s for s in out if s]


def learner_asked_for_example(message: str) -> bool:
    return bool(_EXAMPLE_REQUEST_RE.search(message or ""))


def display_allowed(*, step_just_started: bool, wrong_attempts: int, asked_for_example: bool) -> bool:
    """§9.1: show only when introducing a step, after the 2nd wrong attempt, or on request."""
    return step_just_started or wrong_attempts >= 2 or asked_for_example


def steps_checklist(steps: list[dict], current_index: int, completed: bool) -> list[dict]:
    """The local `steps` checklist. Titles are shown only once a step is unlocked."""
    out = []
    for i, s in enumerate(steps):
        if completed or i < current_index:
            status = "done"
        elif i == current_index:
            status = "current"
        else:
            status = "locked"
        out.append({
            "index": i + 1,
            "title": s.get("title", f"Step {i + 1}") if status != "locked" else "",
            "status": status,
        })
    return out
