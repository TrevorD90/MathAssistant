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
    latex: str = Field(max_length=2000)


class TurnBody(BaseModel):
    text: str = Field(default="", max_length=1000)
    latex: str = Field(default="", max_length=500)


@router.get("/problems")
def list_problems(request: Request):
    return _svc(request).storage.list_problems()


@router.post("/problems")
def start_problem(body: StartBody, request: Request):
    return _svc(request).engine.start_problem(body.latex)


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
