"""Spec §14 — Key & local-only."""

from __future__ import annotations

import socket
from pathlib import Path

import anthropic
import httpx2
import keyring
import pytest

from conftest import BASE, PORT, TOKEN, make_client
from mathassistant import key_store, log_redact
from mathassistant.log_redact import RedactFilter, scrub, setup_logging
from mathassistant.paths import data_dir, log_dir
from mathassistant.providers.anthropic_provider import API_HOST, AnthropicProvider
from mathassistant.providers.base import ProviderError, StructuredRequest
from mathassistant.server import bind_socket
from mathassistant.services import Services

# Fake, key-shaped test values are assembled at runtime so no key-shaped literal
# sits in the repo (keeps GitHub secret scanning / push protection quiet).
PFX = "sk-" + "ant-" + "api03-"
SENTINEL_KEY = PFX + "SENTINELtestKEY" + "0" * 64


def _keyring_usable() -> bool:
    try:
        key_store._check_backend()
        return True
    except key_store.KeyStoreUnavailable:
        return False


def _files_containing(root: Path, needle: str) -> list[Path]:
    hits = []
    for p in root.rglob("*"):
        if p.is_file():
            try:
                if needle.encode() in p.read_bytes():
                    hits.append(p)
            except OSError:
                pass
    return hits


def _auth_error_containing_key(key: str) -> anthropic.AuthenticationError:
    req = httpx2.Request("POST", f"https://{API_HOST}/v1/messages")
    resp = httpx2.Response(401, request=req, headers={"request-id": "req_test"})
    return anthropic.AuthenticationError(f"invalid x-api-key: {key}", response=resp, body=None)


# ------------------------------------------------------------------ key storage

@pytest.mark.keyring
@pytest.mark.skipif(not _keyring_usable(), reason="no OS credential store in this environment")
def test_key_stored_in_os_store_and_nowhere_else(storage, monkeypatch, caplog):
    setup_logging()
    try:
        key_store.set_key("anthropic", SENTINEL_KEY)
        # It is in the OS credential store (under the test service name).
        assert keyring.get_password("mathassistant-test", "anthropic-api-key") == SENTINEL_KEY

        # Force a provider error whose message echoes the key.
        class BadClient:
            class messages:  # noqa: N801
                @staticmethod
                def create(**_):
                    raise _auth_error_containing_key(SENTINEL_KEY)

        provider = AnthropicProvider(api_key=SENTINEL_KEY, model="claude-haiku-4-5", client=BadClient())
        with pytest.raises(ProviderError) as ei:
            provider.structured(StructuredRequest(system_blocks=["s"], messages=[{"role": "user", "content": "x"}],
                                                  schema={"type": "object"}, max_tokens=10))
        assert SENTINEL_KEY not in ei.value.user_message
        import logging

        logging.getLogger("test").error("provider said: invalid x-api-key: %s", SENTINEL_KEY)
        for h in logging.getLogger().handlers:
            h.flush()

        # Settings, DB, config, logs: nothing contains the key.
        storage.set_setting("provider", "anthropic")
        assert _files_containing(data_dir(), SENTINEL_KEY) == []
        assert _files_containing(log_dir(), SENTINEL_KEY) == []
        assert _files_containing(storage.path.parent, SENTINEL_KEY) == []
        assert SENTINEL_KEY not in caplog.text or "[REDACTED]" in caplog.text
    finally:
        key_store.delete_key("anthropic")
        assert keyring.get_password("mathassistant-test", "anthropic-api-key") is None


def test_redaction_filter_scrubs_keys():
    log_redact.register_secret("my-very-secret-value-123")
    assert "my-very-secret-value-123" not in scrub("oops my-very-secret-value-123 leaked")
    assert "sk-ant-" not in scrub("key " + PFX + "abcdefghijklmnop")
    import logging

    rec = logging.LogRecord("x", logging.ERROR, __file__, 1, "k=%s", (PFX + "zzzzzzzzzzzzzzzz",), None)
    RedactFilter().filter(rec)
    assert "sk-ant" not in rec.getMessage()


def test_settings_table_refuses_secrets(storage):
    with pytest.raises(ValueError):
        storage.set_setting("api_key", "x")


def test_plaintext_fallback_is_refused(monkeypatch):
    class Plain:  # a stand-in insecure backend
        pass

    Plain.__module__ = "keyrings.alt.file"
    Plain.__name__ = "PlaintextKeyring"
    monkeypatch.setattr(keyring, "get_keyring", lambda: Plain())
    with pytest.raises(key_store.KeyStoreUnavailable):
        key_store.set_key("anthropic", PFX + "whatever-whatever")


# ------------------------------------------------------------------ onboarding / errors

def test_no_key_shows_onboarding_and_disables_tutoring(storage, monkeypatch):
    monkeypatch.setattr(key_store, "get_key", lambda provider: None)
    c = make_client(storage)  # real provider path, no key
    status = c.get("/api/status").json()
    assert status["has_key"] is False and status["tutoring_enabled"] is False
    r = c.post("/api/problems", json={"latex": "2x+3=7"})
    assert r.status_code == 409 and r.json()["error"] == "no_key"


def test_invalid_key_gives_clear_error_without_echoing_key(storage, monkeypatch):
    bad_key = PFX + "THISISNOTAREALKEY" + "0" * 18

    class BadClient:
        class messages:  # noqa: N801
            @staticmethod
            def create(**_):
                raise _auth_error_containing_key(bad_key)

    from mathassistant.providers import registry

    monkeypatch.setattr(registry, "create_provider",
                        lambda provider, model, key, capabilities=None: AnthropicProvider(key, model, client=BadClient()))
    stored = []
    monkeypatch.setattr(key_store, "set_key", lambda p, k: stored.append(k))
    c = make_client(storage)
    r = c.post("/api/key/test", json={"provider": "anthropic", "model": "claude-haiku-4-5", "key": bad_key})
    assert r.status_code == 401
    body = r.text
    assert bad_key not in body
    assert "rejected" in r.json()["message"]
    assert stored == []                     # an invalid key is not saved


def test_provider_errors_map_to_key_free_messages():
    from mathassistant.providers.anthropic_provider import _map_error

    req = httpx2.Request("POST", f"https://{API_HOST}/v1/messages")
    cases = {
        anthropic.RateLimitError("rl", response=httpx2.Response(429, request=req), body=None): "rate_limited",
        anthropic.BadRequestError("Your credit balance is too low", response=httpx2.Response(400, request=req),
                                  body=None): "no_credits",
        anthropic.InternalServerError("boom", response=httpx2.Response(500, request=req), body=None): "outage",
        anthropic.APIConnectionError(request=req): "network",
        anthropic.PermissionDeniedError("no", response=httpx2.Response(403, request=req), body=None): "permission",
    }
    for exc, kind in cases.items():
        assert _map_error(exc).kind == kind


# ------------------------------------------------------------------ local server

def test_server_binds_loopback_only():
    sock = bind_socket()
    try:
        host, port = sock.getsockname()
        assert host == "127.0.0.1"
        # Try to reach it via this machine's LAN address: must fail.
        lan_ips = {ai[4][0] for ai in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
        lan_ips.discard("127.0.0.1")
        for ip in lan_ips:
            with pytest.raises(OSError):
                socket.create_connection((ip, port), timeout=1).close()
    finally:
        sock.close()


def test_api_without_token_rejected(storage, fake):
    c = make_client(storage, lambda: fake)
    del c.headers["X-Session-Token"]
    assert c.get("/api/status").status_code == 403
    assert c.get("/api/status", headers={"X-Session-Token": "wrong"}).status_code == 403
    assert c.get("/api/status", headers={"X-Session-Token": TOKEN}).status_code == 200


def test_bad_host_and_cross_origin_rejected(storage, fake):
    c = make_client(storage, lambda: fake)
    assert c.get("/api/status", headers={"Host": "evil.example:80"}).status_code == 403
    assert c.get("/api/status", headers={"Host": f"evil.example:{PORT}"}).status_code == 403
    assert c.get("/api/status", headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.get("/api/status", headers={"Origin": BASE}).status_code == 200


def test_security_headers_present(storage, fake):
    c = make_client(storage, lambda: fake)
    r = c.get("/api/status")
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"


def test_only_outbound_traffic_is_the_ai_provider(storage, monkeypatch):
    """Run a session with the real Anthropic adapter and record every DNS/connect attempt."""
    attempted: list[str] = []
    real_getaddrinfo = socket.getaddrinfo

    def spy_getaddrinfo(host, *args, **kwargs):
        if host not in ("127.0.0.1", "localhost", "testserver"):
            attempted.append(str(host))
            raise OSError("network blocked in test")
        return real_getaddrinfo(host, *args, **kwargs)

    def spy_connect(self, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1"):
            attempted.append(str(host))
            raise OSError("network blocked in test")
        return real_connect(self, address)

    real_connect = socket.socket.connect
    monkeypatch.setattr(socket, "getaddrinfo", spy_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", spy_connect)
    monkeypatch.setattr(key_store, "get_key", lambda provider: PFX + "fake-key-for-traffic-test-000000")
    storage.set_setting("key_verified", "1")

    c = make_client(storage)
    c.get("/api/status")
    c.get("/api/problems")
    r = c.post("/api/problems", json={"latex": "2x+3=7"})   # triggers a real (blocked) provider call
    assert r.status_code == 502 and r.json()["error"] == "network"
    assert attempted, "expected the provider call to attempt a connection"
    assert set(attempted) == {API_HOST}


def test_services_status_shape(storage, fake):
    s = Services(storage, provider_factory=lambda: fake)
    st = s.status()
    assert st["model"] == "claude-haiku-4-5"
    assert st["tested"] is True and st["untested_warning"] is None      # passed the live run
    s.set_model("anthropic", "claude-sonnet-5")
    assert s.status()["untested_warning"]                               # not yet live-tested


def test_demo_provider_only_in_dev_mode(storage, monkeypatch):
    monkeypatch.setenv("MATHASSISTANT_DEMO", "1")
    assert Services(storage, dev_mode=False)._provider_factory_override is None
    assert Services(storage, dev_mode=True)._provider_factory_override is not None
