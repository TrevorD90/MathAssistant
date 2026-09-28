"""Launch the local server (spec §3.1).

* Binds 127.0.0.1 only (never 0.0.0.0): other devices can't reach it.
* Uses a fixed default port (51789) so the browser remembers camera
  permission; falls back to a free port (port 0) if it's taken. The bound
  socket is handed to Uvicorn directly (no find-then-bind race).
* Generates a per-launch session token and opens the browser at
  http://127.0.0.1:<port>/#token=<token>. The token is in the URL *fragment*,
  which browsers never send to servers or in Referer headers.
* The UI's Quit button calls /api/quit, which stops Uvicorn.
"""

from __future__ import annotations

import logging
import secrets
import socket
import threading
import webbrowser

import uvicorn

from .app import create_app
from .config import Config

log = logging.getLogger(__name__)

HOST = "127.0.0.1"
# Stable default port: browsers remember camera permission per origin
# (scheme + host + port), so a fixed port means "Allow camera" is asked once.
DEFAULT_PORT = 51789


def bind_socket(port: int | None = None) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        # Windows: never share a port another process is using.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        sock.bind((HOST, port or 0))
        sock.listen(64)
    except OSError:
        sock.close()
        raise
    return sock


def bind_preferred(port: int | None) -> socket.socket:
    """Bind the preferred port; if it's taken, fall back to any free port."""
    if port:
        try:
            return bind_socket(port)
        except OSError:
            log.info("port %d is in use; using a free port instead", port)
    return bind_socket(None)


def run(config: Config) -> None:
    token = secrets.token_urlsafe(32)
    sock = bind_preferred(config.fixed_port or DEFAULT_PORT)
    port = sock.getsockname()[1]

    app = create_app(token=token, port_getter=lambda: port, dev_mode=config.dev_mode)
    uv_config = uvicorn.Config(app, log_level="warning", access_log=False, lifespan="off")
    server = uvicorn.Server(uv_config)
    app.state.services.shutdown = lambda: setattr(server, "should_exit", True)

    url = f"http://{HOST}:{port}/#token={token}"
    log.info("MathAssistant listening on http://%s:%d", HOST, port)  # token deliberately not logged
    print(f"MathAssistant is running. If your browser didn't open, visit:\n  {url}\nPress Ctrl+C to stop.",
          flush=True)
    if config.open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    server.run(sockets=[sock])
    log.info("MathAssistant stopped")
