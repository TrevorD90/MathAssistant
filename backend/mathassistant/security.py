"""Local-server protections (spec §3.1).

* Host header must be 127.0.0.1:<port> or localhost:<port> (blocks DNS
  rebinding: a malicious site resolving its own name to 127.0.0.1).
* Every /api request must carry the per-launch session token in the
  `X-Session-Token` header. Browsers never attach custom headers cross-origin
  without a CORS preflight, and we never answer preflights, so other websites
  in the same browser can't call the API (which can spend the user's key).
* A cross-origin `Origin` header on /api is rejected outright.
* Strict security headers on every response (CSP: same-origin only).
"""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

TOKEN_HEADER = "x-session-token"

CSP = (
    "default-src 'self'; "
    # 'wasm-unsafe-eval': pdf.js decodes some PDF images with bundled WebAssembly
    # (only compiles WASM served from this origin; no JS eval).
    "script-src 'self' 'wasm-unsafe-eval'; "
    "worker-src 'self' blob:; "
    # KaTeX and MathLive set inline styles on rendered math.
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self' data:; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)


class LocalOnlyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, token: str, port_getter):
        super().__init__(app)
        self._token = token
        self._port_getter = port_getter  # port known only after the socket binds

    def _allowed_hosts(self) -> set[str]:
        port = self._port_getter()
        return {f"127.0.0.1:{port}", f"localhost:{port}"}

    async def dispatch(self, request: Request, call_next) -> Response:
        host = request.headers.get("host", "")
        if host not in self._allowed_hosts():
            return JSONResponse({"error": "bad_host", "message": "Forbidden"}, status_code=403)

        if request.url.path.startswith("/api"):
            origin = request.headers.get("origin")
            if origin and origin not in {f"http://{h}" for h in self._allowed_hosts()}:
                return JSONResponse({"error": "bad_origin", "message": "Forbidden"}, status_code=403)
            supplied = request.headers.get(TOKEN_HEADER, "")
            if not hmac.compare_digest(supplied.encode(), self._token.encode()):
                return JSONResponse({"error": "bad_token", "message": "Forbidden"}, status_code=403)

        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        # Camera only for this page; no microphone, location, etc.
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=(), payment=()"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api") else "no-cache"
        return response
