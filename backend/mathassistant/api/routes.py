"""HTTP API (all under /api; token-protected by LocalOnlyMiddleware).

Plain JSON request/response. Replies are fully leak-guarded before they are
returned, so nothing is streamed (see CLAUDE.md decision log).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..engine.turn_loop import TutorError
from ..providers import registry
from ..services import Services

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# TutorError.kind -> HTTP status
_STATUS = {
    "not_found": 404,
    "no_key": 409, "key_not_verified": 409, "keystore_unavailable": 503,
    "invalid_key": 401, "permission": 403, "no_credits": 402, "rate_limited": 429,
    "outage": 502, "network": 502, "model_not_found": 400, "missing_capability": 400,
    "bad_image": 400,
}


def _svc(request: Request) -> Services:
    return request.app.state.services


def error_response(err: TutorError) -> JSONResponse:
    return JSONResponse({"error": err.kind, "message": err.user_message},
                        status_code=_STATUS.get(err.kind, 400))


# ------------------------------------------------------------------ system

@router.get("/status")
def status(request: Request):
    return _svc(request).status()


@router.get("/providers")
def providers():
    return {"providers": registry.catalog(), "default_provider": registry.DEFAULT_PROVIDER,
            "default_model": registry.DEFAULT_MODEL, "untested_warning": registry.UNTESTED_WARNING}


@router.post("/quit")
def quit_app(request: Request):
    log.info("quit requested from UI")
    _svc(request).shutdown()
    return {"ok": True}


# ------------------------------------------------------------------ settings

class ModelBody(BaseModel):
    provider: str = Field(max_length=40)
    model: str = Field(max_length=100)


class KeyTestBody(ModelBody):
    key: str | None = Field(default=None, max_length=400)


@router.post("/settings/model")
def set_model(body: ModelBody, request: Request):
    _svc(request).set_model(body.provider, body.model)
    return _svc(request).status()


@router.post("/key/test")
def test_key(body: KeyTestBody, request: Request):
    svc = _svc(request)
    result = svc.test_key(body.provider, body.model, body.key)
    return {**result, "status": svc.status()}


@router.delete("/key")
def remove_key(request: Request, provider: str = "anthropic"):
    svc = _svc(request)
    svc.remove_key(provider)
    return svc.status()


# ------------------------------------------------------------------ problems

class StartBody(BaseModel):
    latex: str = Field(default="", max_length=2000)
    text: str = Field(default="", max_length=2000)   # word problem (plain text)
    # Vision call(s) this problem came from (a multi-page PDF can be several).
    extraction_ids: list[str] = Field(default_factory=list, max_length=20)
    queued_id: str | None = Field(default=None, max_length=40)  # started from "Up next"


class QueueItem(BaseModel):
    kind: str = Field(pattern="^(math|words)$")
    latex: str = Field(default="", max_length=2000)
    text: str = Field(default="", max_length=2000)
    label: str = Field(default="", max_length=20)
    instruction: str = Field(default="", max_length=200)


class QueueBody(BaseModel):
    items: list[QueueItem] = Field(max_length=200)
    source: str = Field(default="", max_length=120)


class ExtractBody(BaseModel):
    # base64 of a cropped, downscaled image (5 MB decoded max -> ~7 MB base64)
    image_base64: str = Field(max_length=7_200_000)
    media_type: str = Field(max_length=20)


class TurnBody(BaseModel):
    text: str = Field(default="", max_length=1000)
    latex: str = Field(default="", max_length=500)


@router.get("/problems")
def list_problems(request: Request):
    return _svc(request).storage.list_problems()


@router.post("/extract")
def extract(body: ExtractBody, request: Request):
    """Phase 2: image -> problem text to confirm. One vision call; the image isn't stored."""
    return _svc(request).extract_image(body.image_base64, body.media_type)


@router.post("/problems")
def start_problem(body: StartBody, request: Request):
    svc = _svc(request)
    extra = svc.take_extraction_usage([e for e in body.extraction_ids if isinstance(e, str)][:20])
    view = svc.engine.start_problem(body.latex, body.text, extra_usage=extra)
    if body.queued_id:
        svc.storage.delete_queued(body.queued_id)   # started: no longer "up next"
    return view


@router.post("/queue")
def add_to_queue(body: QueueBody, request: Request):
    """Save not-yet-started problems (e.g. the rest of a worksheet). No AI calls."""
    items = [{"problem_text": (i.latex if i.kind == "math" else i.text).strip(), "problem_kind": i.kind,
              "label": i.label, "instruction": i.instruction} for i in body.items]
    items = [i for i in items if i["problem_text"]]
    ids = _svc(request).storage.add_queued(items, source=body.source)
    return {"ok": True, "added": len(ids)}


@router.delete("/queue/{queued_id}")
def delete_queued(queued_id: str, request: Request):
    if not _svc(request).storage.delete_queued(queued_id):
        raise TutorError("That problem wasn't found.", "not_found")
    return {"ok": True}


@router.get("/problems/{problem_id}")
def get_problem(problem_id: str, request: Request):
    return _svc(request).engine.load(problem_id)


@router.post("/problems/{problem_id}/turn")
def turn(problem_id: str, body: TurnBody, request: Request):
    return _svc(request).engine.submit(problem_id, text=body.text, latex=body.latex)


@router.delete("/problems/{problem_id}")
def delete_problem(problem_id: str, request: Request):
    if not _svc(request).storage.delete_problem(problem_id):
        raise TutorError("That problem wasn't found.", "not_found")
    return {"ok": True}


@router.delete("/problems")
def delete_all(request: Request):
    n = _svc(request).storage.delete_all_problems()
    return {"ok": True, "deleted": n}
