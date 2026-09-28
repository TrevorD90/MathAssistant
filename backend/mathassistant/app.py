"""FastAPI application factory: API + the built frontend as static files."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import error_response, router
from .engine.turn_loop import TutorError
from .paths import web_dist_dir
from .providers.base import LLMProvider
from .security import LocalOnlyMiddleware
from .services import Services
from .storage import Storage

log = logging.getLogger(__name__)

# Windows' registry often lacks these; browsers refuse module workers (pdf.js)
# and streaming WebAssembly served with the wrong Content-Type.
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("font/ttf", ".ttf")


def create_app(*, token: str, port_getter: Callable[[], int], storage: Storage | None = None,
               provider_factory: Callable[[], LLMProvider] | None = None,
               dev_mode: bool = False, web_dir: Path | None = None) -> FastAPI:
    # No OpenAPI/docs routes: nothing extra exposed on the local port.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.services = Services(storage or Storage(), provider_factory=provider_factory, dev_mode=dev_mode)
    app.add_middleware(LocalOnlyMiddleware, token=token, port_getter=port_getter)
    app.include_router(router)

    @app.exception_handler(TutorError)
    async def _tutor_error(_: Request, exc: TutorError):
        return error_response(exc)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        # Log type only via the redacting logger; never echo internals to the client.
        log.exception("unhandled error: %s", type(exc).__name__)
        return JSONResponse({"error": "internal", "message": "Something went wrong. Try again."}, status_code=500)

    dist = web_dir or web_dist_dir()
    if (dist / "index.html").exists():
        if (dist / "assets").exists():
            app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            # Serve top-level static files (fonts, icons) if present, else the SPA shell.
            if path.startswith("api/"):
                return JSONResponse({"error": "not_found", "message": "Not found"}, status_code=404)
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            if "." in Path(path).name:
                # A missing file (font, script...) is a 404, not the app page.
                return JSONResponse({"error": "not_found", "message": "Not found"}, status_code=404)
            return FileResponse(dist / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        async def no_build():
            return JSONResponse({"error": "web_not_built",
                                 "message": "Frontend not built. Run: cd web && npm install && npm run build"},
                                status_code=503)

    return app
