"""Launch the local server (spec §3.1).

* Binds 127.0.0.1 only (never 0.0.0.0): other devices can't reach it.
* Uses a fixed default port (51789) so the browser remembers camera
  permission; falls back to a free port (port 0) if it's taken. The bound
  socket is handed to Uvicorn directly (no find-then-bind race).
* Generates a per-launch session token and opens the browser at
  http://127.0.0.1:<port>/#token=<token>. The token is in the URL *fragment*,
  which browsers never send to servers or in Referer headers.
* The UI's Quit button calls /api/quit, which stops Uvicorn.
* Bundled builds (Phase 3) show a small control window; closing it stops the
  server. Only one copy runs at a time: a second launch reopens the first.
"""

from __future__ import annotations

import logging
import secrets
import socket
import sys
import threading
import webbrowser

import uvicorn

from . import __version__, control_window, instance
from .app import create_app
from .config import Config
from .paths import is_frozen

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


def _say(msg: str) -> None:
    """Print for terminal users; windowed (no-console) builds have no stdout."""
    if sys.stdout is not None:
        try:
            print(msg, flush=True)
        except (OSError, ValueError):
            pass


def run(config: Config, *, window: bool | None = None) -> None:
    """Start MathAssistant. `window`: show the control window (default: in bundled builds)."""
    # One copy at a time: if MathAssistant is already running, just reopen it.
    existing = instance.running_instance_url()
    if existing:
        log.info("MathAssistant is already running; reopening it")
        if config.open_browser:
            webbrowser.open(existing)
        _say("MathAssistant is already running; opened it in your browser.")
        return

    token = secrets.token_urlsafe(32)
    sock = bind_preferred(config.fixed_port or DEFAULT_PORT)
    port = sock.getsockname()[1]

    app = create_app(token=token, port_getter=lambda: port, dev_mode=config.dev_mode)
    services = app.state.services
    if services.update_check_enabled():
        services.updates.start_background()   # optional; never blocks (§12.4)

    # log_config=None: keep our redacting logging; uvicorn's default config
    # writes to stderr, which doesn't exist in windowed builds.
    uv_config = uvicorn.Config(app, log_level="warning", access_log=False, lifespan="off", log_config=None)
    server = uvicorn.Server(uv_config)
    stopped = threading.Event()

    def stop() -> None:
        server.should_exit = True

    services.shutdown = stop

    url = f"http://{HOST}:{port}/#token={token}"
    log.info("MathAssistant %s listening on http://%s:%d", __version__, HOST, port)  # token never logged
    instance.write_session(port, token)
    use_window = window if window is not None else (is_frozen() and control_window.available())
    try:
        if use_window:
            def serve() -> None:
                try:
                    server.run(sockets=[sock])
                finally:
                    stopped.set()

            thread = threading.Thread(target=serve, name="server", daemon=True)
            thread.start()
            if config.open_browser:
                threading.Timer(0.6, lambda: webbrowser.open(url)).start()
            control_window.run(url, __version__, is_stopped=stopped.is_set, stop=stop)  # blocks (main thread)
            stop()
            thread.join(timeout=5)
        else:
            _say(f"MathAssistant is running. If your browser didn't open, visit:\n  {url}\nPress Ctrl+C to stop.")
            if config.open_browser:
                threading.Timer(0.6, lambda: webbrowser.open(url)).start()
            server.run(sockets=[sock])
    finally:
        instance.clear_session(token)
        log.info("MathAssistant stopped")


def self_test() -> int:
    """Smoke test for built apps (used by CI): start the server on a free port,
    call the API with the token, serve the web app, parse and solve some math,
    then stop. Returns a process exit code (0 = OK). Makes no AI calls."""
    import urllib.request

    from .engine.solver import solve_latex

    try:
        assert solve_latex(r"\frac{d}{dx}\sin(x^2)").kind == "expression"
        assert solve_latex("2x+3=7").kind == "solutions"
        token = secrets.token_urlsafe(16)
        sock = bind_socket(None)
        port = sock.getsockname()[1]
        app = create_app(token=token, port_getter=lambda: port)
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off", log_config=None))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        base = f"http://{HOST}:{port}"
        for _ in range(50):
            if server.started:
                break
            threading.Event().wait(0.1)
        req = urllib.request.Request(f"{base}/api/status", headers={"X-Session-Token": token})
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 200
        with urllib.request.urlopen(f"{base}/", timeout=5) as r:
            assert r.status == 200 and b"<div id=\"root\">" in r.read()
        server.should_exit = True
        thread.join(timeout=5)
        _say("self-test OK")
        return 0
    except Exception as exc:  # report and fail
        log.error("self-test failed: %s: %s", type(exc).__name__, exc)
        _say(f"self-test FAILED: {type(exc).__name__}: {exc}")
        return 1
