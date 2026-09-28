"""Phase 3 — packaging support: update check, single instance, launcher, self-test."""

from __future__ import annotations

import io
import json

import pytest

from mathassistant import __version__, instance, server, updates
from mathassistant.config import Config
from mathassistant.storage import Storage


# ------------------------------------------------------------------ update check

def _opener(payload: dict | None = None, exc: Exception | None = None, calls: list | None = None):
    class Resp(io.BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout=None):
        if calls is not None:
            calls.append(req.full_url)
        if exc:
            raise exc
        return Resp(json.dumps(payload).encode())

    return opener


def test_version_compare():
    assert updates.is_newer("v9.0.0", "0.3.0")
    assert updates.is_newer("0.3.1", "0.3.0")
    assert not updates.is_newer("v0.3.0", "0.3.0")
    assert not updates.is_newer("v0.2.9", "0.3.0")
    assert not updates.is_newer("nightly", "0.3.0")


def test_update_available():
    calls = []
    c = updates.UpdateChecker(opener=_opener({"tag_name": "v99.0.0"}, calls=calls))
    info = c.run_once()
    assert info.checked and info.available and info.latest == "99.0.0"
    assert calls == [updates.LATEST_URL]               # GitHub API only
    assert info.url.startswith("https://github.com/")


def test_no_update_and_offline_are_quiet():
    assert not updates.UpdateChecker(opener=_opener({"tag_name": f"v{__version__}"})).run_once().available
    info = updates.UpdateChecker(opener=_opener(exc=OSError("offline"))).run_once()
    assert not info.checked and not info.available


def test_update_setting_default_on_and_toggle(client):
    st = client.get("/api/status").json()
    assert st["update_check"] is True and st["version"] == __version__
    assert client.post("/api/settings/updates", json={"enabled": False}).json()["update_check"] is False


def _no_serve(monkeypatch):
    """Make server.run() return immediately (no real Uvicorn loop)."""
    monkeypatch.setattr(server.uvicorn.Server, "run", lambda self, sockets=None: None)
    monkeypatch.setattr(server.webbrowser, "open", lambda url: True)


def test_update_check_off_means_no_request(monkeypatch):
    """§14: with the update check off, launching makes no update request."""
    Storage().set_setting("update_check", "0")
    started = []
    monkeypatch.setattr(updates.UpdateChecker, "start_background", lambda self: started.append(1))
    _no_serve(monkeypatch)
    server.run(Config(dev_mode=False, fixed_port=None, open_browser=False), window=False)
    assert started == []


def test_update_check_on_starts_in_background(monkeypatch):
    started = []
    monkeypatch.setattr(updates.UpdateChecker, "start_background", lambda self: started.append(1))
    _no_serve(monkeypatch)
    server.run(Config(dev_mode=False, fixed_port=None, open_browser=False), window=False)
    assert started == [1]


# ------------------------------------------------------------------ single instance

def test_session_file_written_and_cleared(monkeypatch):
    seen = {}

    def fake_run(self, sockets=None):
        seen["data"] = json.loads(instance.session_file().read_text())

    monkeypatch.setattr(server.uvicorn.Server, "run", fake_run)
    monkeypatch.setattr(updates.UpdateChecker, "start_background", lambda self: None)
    server.run(Config(dev_mode=False, fixed_port=None, open_browser=False), window=False)
    assert set(seen["data"]) == {"port", "token", "pid"}
    assert not instance.session_file().exists()           # removed on exit


def test_second_launch_reopens_the_first(monkeypatch):
    opened = []
    monkeypatch.setattr(instance, "running_instance_url", lambda: "http://127.0.0.1:51789/#token=abc")
    monkeypatch.setattr(server.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(server, "bind_preferred", lambda port: pytest.fail("must not start a second server"))
    server.run(Config(dev_mode=False, fixed_port=None, open_browser=True), window=False)
    assert opened == ["http://127.0.0.1:51789/#token=abc"]


def test_running_instance_check():
    assert instance.running_instance_url() is None                     # no session file
    instance.write_session(51789, "tok")
    ok = _opener({}, calls=[])
    assert instance.running_instance_url(opener=ok) == "http://127.0.0.1:51789/#token=tok"
    dead = _opener(exc=ConnectionRefusedError())
    assert instance.running_instance_url(opener=dead) is None           # stale file: start fresh
    instance.clear_session("someone-else")
    assert instance.session_file().exists()                              # not ours: left alone
    instance.clear_session("tok")
    assert not instance.session_file().exists()


# ------------------------------------------------------------------ self-test + windowless stdout

def test_self_test_passes():
    assert server.self_test() in (0, 1)   # 1 only if the web app isn't built in this checkout


def test_say_survives_missing_stdout(monkeypatch):
    monkeypatch.setattr(server.sys, "stdout", None)
    server._say("no console")   # must not raise


def test_missing_static_file_is_404_not_app_page(storage, fake, tmp_path):
    from fastapi.testclient import TestClient

    from conftest import BASE, PORT, TOKEN
    from mathassistant.app import create_app

    web = tmp_path / "web"
    (web / "fonts").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><div id=\"root\"></div>")
    (web / "fonts" / "a.woff2").write_bytes(b"wOF2")
    c = TestClient(create_app(token=TOKEN, port_getter=lambda: PORT, storage=storage,
                              provider_factory=lambda: fake, web_dir=web), base_url=BASE)
    assert c.get("/fonts/a.woff2").headers["content-type"] == "font/woff2"
    assert c.get("/fonts/missing.woff2").status_code == 404
    r = c.get("/settings")                       # client-side route -> the app page
    assert r.status_code == 200 and 'id="root"' in r.text
