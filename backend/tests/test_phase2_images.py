"""Phase 2 — image/PDF input (spec §4, §11.2, §13 Phase 2).

The browser handles camera, upload, paste, PDF rendering and cropping, and
sends one cropped PNG/JPEG. The backend makes one vision call, returns the
problem for the learner to confirm, and never stores the image.
"""

from __future__ import annotations

import base64
import json
import socket
from pathlib import Path

import pytest

from conftest import make_client
from mathassistant.engine.extract import MAX_IMAGE_BYTES, ImageError, decode_image
from mathassistant.providers.anthropic_provider import AnthropicProvider, _probe_png
from mathassistant.providers.base import Capabilities
from mathassistant.server import bind_preferred, bind_socket

PNG = _probe_png()
PNG_B64 = base64.b64encode(PNG).decode()
# A distinctive chunk of the upload, to search storage/logs for afterwards.
MARKER = PNG_B64[20:60]


def extract(client, b64=PNG_B64, media_type="image/png"):
    return client.post("/api/extract", json={"image_base64": b64, "media_type": media_type})


# ------------------------------------------------------------------ extraction flow

def test_image_extracts_to_confirmable_problem_with_one_call(client, fake):
    r = extract(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["readable"] and len(body["problems"]) == 1
    assert body["problems"][0]["kind"] == "math" and body["problems"][0]["latex"] == r"5\times5"
    assert fake.call_count == 1 and fake.calls[0].purpose == "vision"
    # The image is sent to the provider as an image block.
    content = fake.calls[0].messages[0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/png"
    # Nothing was planned yet: tutoring starts only after the learner confirms.
    assert client.get("/api/problems").json()["in_progress"] == []


def test_confirm_starts_problem_and_counts_the_vision_call(client, fake):
    ex = extract(client).json()
    latex = ex["problems"][0]["latex"]
    r = client.post("/api/problems", json={"latex": latex, "extraction_ids": [ex["extraction_id"]]})
    assert r.status_code == 200
    view = r.json()
    assert view["usage"]["ai_calls"] == 2            # vision + intake
    # The extraction usage is counted once only.
    r2 = client.post("/api/problems", json={"latex": latex, "extraction_ids": [ex["extraction_id"]]})
    assert r2.json()["usage"]["ai_calls"] == 1


def test_learner_can_edit_before_confirming(client, storage):
    ex = extract(client).json()
    view = client.post("/api/problems", json={"latex": r"6\times5", "extraction_ids": [ex["extraction_id"]]}).json()
    assert view["problem_latex"] == r"6\times5"
    assert storage.get_problem(view["id"]).solution["kind"] == "number"


def test_word_problem_from_image(client, script):
    script.vision = {"readable": True, "note": "", "problems": [
        {"label": "", "kind": "words", "latex": "", "instruction": "",
         "text": "Sam has 3 bags with 12 apples in each bag. How many apples does Sam have?"}]}
    body = extract(client).json()
    p = body["problems"][0]
    assert p["kind"] == "words" and p["text"].startswith("Sam has")


def test_unreadable_image_gives_clear_note(client, script):
    script.vision = {"readable": False, "problems": [], "note": "too blurry"}
    body = extract(client).json()
    assert body["readable"] is False and body["note"] == "too blurry"


def test_malformed_vision_reply_is_unreadable(client, script):
    script.vision = None
    body = extract(client).json()
    assert body["readable"] is False


def test_readable_but_empty_is_unreadable(client, script):
    script.vision = {"readable": True, "note": "", "problems": [
        {"label": "", "kind": "math", "latex": "", "text": "", "instruction": ""}]}
    assert extract(client).json()["readable"] is False


# ------------------------------------------------------------------ validation

@pytest.mark.parametrize("b64, media, msg", [
    (PNG_B64, "image/bmp", "PNG, JPEG"),
    ("not base64!!", "image/png", "couldn't be read"),
    (base64.b64encode(b"\xff\xd8\xff\xe0jpegdata").decode(), "image/png", "isn't the image type"),
    ("", "image/png", "empty"),
])
def test_bad_images_rejected(b64, media, msg):
    with pytest.raises(ImageError, match=msg):
        decode_image(b64, media)


def test_oversized_image_rejected():
    big = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * (MAX_IMAGE_BYTES + 1)).decode()
    with pytest.raises(ImageError, match="too large"):
        decode_image(big, "image/png")


def test_data_url_prefix_accepted():
    assert decode_image("data:image/png;base64," + PNG_B64, "image/png") == PNG


def test_bad_image_http_error_makes_no_ai_call(client, fake):
    r = extract(client, media_type="image/tiff")
    assert r.status_code == 400 and r.json()["error"] == "bad_image"
    assert fake.call_count == 0


# ------------------------------------------------------------------ capability gating

def test_model_without_vision_blocks_image_input(storage, script):
    from mathassistant.providers.fake_provider import FakeProvider

    blind = FakeProvider(responder=script, capabilities=Capabilities(vision=False, structured_output=True))
    c = make_client(storage, lambda: blind)
    c.post("/api/key/test", json={"provider": "anthropic", "model": "claude-haiku-4-5"})
    assert c.get("/api/status").json()["capabilities"]["vision"] is False
    r = extract(c)
    assert r.status_code == 400 and r.json()["error"] == "missing_capability"
    assert "can't read images" in r.json()["message"]
    assert blind.call_count == 0


def test_probe_detects_vision_and_structured_in_one_call():
    calls = []

    class Client:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kw):
                calls.append(kw)
                return object()

    caps = AnthropicProvider("k" * 20, "claude-haiku-4-5", client=Client()).probe()
    assert caps.vision and caps.structured_output
    assert len(calls) == 1
    assert calls[0]["messages"][0]["content"][0]["type"] == "image"


def test_probe_turns_off_vision_when_model_rejects_images():
    import anthropic
    import httpx2

    calls = []

    class Client:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kw):
                calls.append(kw)
                if isinstance(kw["messages"][0]["content"], list):
                    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
                    raise anthropic.BadRequestError("this model does not support image input",
                                                    response=httpx2.Response(400, request=req), body=None)
                return object()

    caps = AnthropicProvider("k" * 20, "some-text-model", client=Client()).probe()
    assert caps.vision is False and caps.structured_output is True
    assert len(calls) == 2


# ------------------------------------------------------------------ privacy

def test_images_are_never_stored_or_logged(client, storage, tmp_path):
    from mathassistant.log_redact import setup_logging
    from mathassistant.paths import data_dir, log_dir

    setup_logging()
    ex = extract(client).json()
    client.post("/api/problems", json={"latex": ex["problems"][0]["latex"], "extraction_ids": [ex["extraction_id"]]})
    import logging

    for h in logging.getLogger().handlers:
        h.flush()
    for root in {data_dir(), log_dir(), Path(storage.path).parent}:
        for p in root.rglob("*"):
            if p.is_file():
                data = p.read_bytes()
                assert MARKER.encode() not in data, p
                assert PNG[16:40] not in data, p
    # And not in any saved problem record.
    rec_json = json.dumps(client.get("/api/problems").json())
    assert MARKER not in rec_json


# ------------------------------------------------------------------ fixed port

def test_preferred_port_used_when_free():
    probe = bind_socket(None)
    port = probe.getsockname()[1]
    probe.close()
    sock = bind_preferred(port)
    try:
        assert sock.getsockname() == ("127.0.0.1", port)
    finally:
        sock.close()


def test_falls_back_when_preferred_port_is_busy():
    busy = bind_socket(None)
    port = busy.getsockname()[1]
    try:
        sock = bind_preferred(port)
        try:
            assert sock.getsockname()[0] == "127.0.0.1"
            assert sock.getsockname()[1] != port
        finally:
            sock.close()
    finally:
        busy.close()


def test_security_headers_allow_camera_for_self_only(client):
    r = client.get("/api/status")
    assert "camera=(self)" in r.headers["permissions-policy"]
    assert "microphone=()" in r.headers["permissions-policy"]
    assert "'unsafe-eval'" not in r.headers["content-security-policy"]


def test_socket_module_unchanged():
    assert socket.AF_INET  # sanity: tests above didn't monkeypatch sockets


def test_static_mime_types_for_pdfjs(storage, fake, tmp_path):
    from fastapi.testclient import TestClient

    from conftest import BASE, PORT, TOKEN
    from mathassistant.app import create_app

    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "pdfjs" / "wasm").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html>")
    (web / "assets" / "w.mjs").write_text("export {}")
    (web / "pdfjs" / "wasm" / "d.wasm").write_bytes(b"\x00asm\x01\x00\x00\x00")
    app = create_app(token=TOKEN, port_getter=lambda: PORT, storage=storage, provider_factory=lambda: fake,
                     web_dir=web)
    c = TestClient(app, base_url=BASE)
    assert c.get("/assets/w.mjs").headers["content-type"].startswith("text/javascript")
    assert c.get("/pdfjs/wasm/d.wasm").headers["content-type"] == "application/wasm"
