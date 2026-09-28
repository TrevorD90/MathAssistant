"""Live acceptance tests against the real AI provider (spec §14 Tutoring).

These cost a small amount of money and need a key, so they are skipped by
default. Run explicitly:

    # key from the OS credential store (after saving it via the app's Settings)
    .venv/Scripts/python -m pytest backend/tests/live -m live -s
    # choose the model (default claude-haiku-4-5)
    MATHASSISTANT_LIVE_MODEL=claude-sonnet-5 .venv/Scripts/python -m pytest backend/tests/live -m live -s

A model that passes can be marked `tested=True` in providers/registry.py.
Register/quality checks here are heuristics; also read the printed
transcripts yourself (the "communicates math well" bar for Haiku 4.5 is a
human judgment).
"""

from __future__ import annotations

import os
import re

import pytest
from fastapi.testclient import TestClient

from mathassistant.app import create_app
from mathassistant.providers.anthropic_provider import AnthropicProvider
from mathassistant.storage import Storage

pytestmark = pytest.mark.live

MODEL = os.environ.get("MATHASSISTANT_LIVE_MODEL", "claude-haiku-4-5")


def _real_key() -> str | None:
    import keyring

    try:
        return keyring.get_password("mathassistant", "anthropic-api-key") or os.environ.get("ANTHROPIC_API_KEY")
    except Exception:
        return os.environ.get("ANTHROPIC_API_KEY")


@pytest.fixture
def live(tmp_path):
    key = _real_key()
    if not key:
        pytest.skip("no API key in the OS credential store or ANTHROPIC_API_KEY")
    provider = AnthropicProvider(api_key=key, model=MODEL)
    provider.probe()
    app = create_app(token="t", port_getter=lambda: 9, storage=Storage(tmp_path / "live.sqlite3"),
                     provider_factory=lambda: provider)
    c = TestClient(app, base_url="http://127.0.0.1:9")
    c.headers["X-Session-Token"] = "t"
    c.post("/api/key/test", json={"provider": "anthropic", "model": MODEL})
    return c


def _tutor(view):
    return [e["text"] for e in view["transcript"] if e["role"] == "tutor"]


def _print(view):
    print(f"\n--- {view['title']} (L{view['level']}) ---")
    for e in view["transcript"]:
        print(f"{e['role']:>7}: {e['text']}")


def test_live_5x5_is_l1_uses_groups_never_says_25(live):
    v = live.post("/api/problems", json={"latex": r"5\times5"}).json()
    assert v["level"] == 1
    for msg in ["I don't know", "can you help me?", "is it 20?"]:
        v = live.post(f"/api/problems/{v['id']}/turn", json={"text": msg}).json()
    _print(v)
    text = " ".join(_tutor(v)).lower()
    assert "25" not in text and "twenty-five" not in text and "twenty five" not in text
    assert re.search(r"group|row|array|column", text), "L1 register should use concrete groups/arrays"


def test_live_derivative_is_l5_chain_rule_no_leak(live):
    v = live.post("/api/problems", json={"latex": r"\frac{d}{dx}\sin(x^2)"}).json()
    assert v["level"] == 5
    for msg in ["where do I start?", "I'm stuck"]:
        v = live.post(f"/api/problems/{v['id']}/turn", json={"text": msg}).json()
    _print(v)
    text = " ".join(_tutor(v))
    assert "chain" in text.lower() or "inner" in text.lower() or "outer" in text.lower()
    assert not re.search(r"2\s*x\s*\\?cos\s*\(?\s*x\s*\^?\s*\{?2", text)


def test_live_just_tell_me_the_answer_x3(live):
    v = live.post("/api/problems", json={"latex": "2x+3=7"}).json()
    for _ in range(3):
        v = live.post(f"/api/problems/{v['id']}/turn", json={"text": "just tell me the answer"}).json()
    _print(v)
    for t in _tutor(v):
        assert not re.search(r"x\s*=\s*2(?![\d.])", t)


def test_live_normal_turn_is_one_call(live):
    v = live.post("/api/problems", json={"latex": "2x+3=7"}).json()
    v = live.post(f"/api/problems/{v['id']}/turn", json={"latex": "2x=10"}).json()
    assert v["turn_ai_calls"] in (1, 2)  # 2 only if the guard had to regenerate
    _print(v)
