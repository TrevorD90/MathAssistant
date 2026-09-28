"""One copy at a time (Phase 3).

A running app writes `session.json` (port, token, pid) to the data folder.
Opening the app again finds it, checks the server really answers with that
token, and just opens the browser to it instead of starting a second server.

The token file is only readable by the same OS user, who could equally read
the key from their own credential store, so it adds no new exposure.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path

from .paths import data_dir

log = logging.getLogger(__name__)


def session_file() -> Path:
    return data_dir() / "session.json"


def write_session(port: int, token: str) -> None:
    p = session_file()
    p.write_text(json.dumps({"port": port, "token": token, "pid": os.getpid()}), encoding="utf-8")
    try:
        os.chmod(p, 0o600)   # owner-only on macOS; Windows user profile folders are already per-user
    except OSError:
        pass


def clear_session(token: str) -> None:
    """Remove the session file, but only if it is ours (a newer instance may own it)."""
    p = session_file()
    try:
        if json.loads(p.read_text(encoding="utf-8")).get("token") == token:
            p.unlink()
    except (OSError, ValueError):
        pass


def running_instance_url(opener=urllib.request.urlopen) -> str | None:
    """URL (with token) of an already-running MathAssistant, if one answers."""
    try:
        data = json.loads(session_file().read_text(encoding="utf-8"))
        port, token = int(data["port"]), str(data["token"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/status", headers={"X-Session-Token": token})
    try:
        with opener(req, timeout=2) as resp:
            if resp.status == 200:
                return f"http://127.0.0.1:{port}/#token={token}"
    except Exception:
        pass
    return None
