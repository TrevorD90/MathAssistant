"""Shared fixtures.

* Every test gets its own data dir (SQLite + logs) and a separate keyring
  service name, so the real app data and stored key are never touched.
* `scripted` is a FakeProvider whose responses are driven by the test: intake
  returns a plan per problem; turns return whatever the test queues.
"""

from __future__ import annotations

import os
import re
from collections import deque

import pytest
from fastapi.testclient import TestClient

from mathassistant.app import create_app
from mathassistant.providers.fake_provider import FakeProvider
from mathassistant.storage import Storage

TOKEN = "test-token-abc123"
PORT = 8123
BASE = f"http://127.0.0.1:{PORT}"

PLANS = {
    r"5\times5": {
        "level": 1, "title": "Multiply five by five", "final_answer_latex": "25",
        "steps": [
            {"title": "Picture the groups", "goal": "See 5x5 as 5 groups of 5.", "result_latex": "",
             "first_question": "How many groups of 5 apples do we have?",
             "check_question": "Why do 5 groups show 5 times 5?", "safe_hint": "Draw one group of 5 dots."},
            {"title": "Count all the apples", "goal": "Count the total.", "result_latex": "25",
             "first_question": "Count by fives. How many apples in all?",
             "check_question": "How did counting by fives help?", "safe_hint": "Say 5, 10, ... and keep going."},
        ],
    },
    r"\frac{d}{dx}\sin(x^2)": {
        "level": 5, "title": "Derivative of sin(x^2)", "final_answer_latex": r"2x\cos(x^2)",
        "steps": [
            {"title": "Identify inner function", "goal": "Find the inner function u.", "result_latex": "u = x^2",
             "first_question": "Which function sits inside the sine?",
             "check_question": "Why is that the inner function?", "safe_hint": "Look at the argument of sin."},
            {"title": "Differentiate the outer", "goal": "Differentiate sin(u) with respect to u.",
             "result_latex": r"\cos(u)", "first_question": "What is the derivative of sin with respect to its argument?",
             "check_question": "Why do we treat u as the variable here?", "safe_hint": "Recall the derivative of sine."},
            {"title": "Differentiate the inner", "goal": "Find du/dx.", "result_latex": "2x",
             "first_question": "What is the derivative of the inner function?",
             "check_question": "Which rule gives that?", "safe_hint": "Use the power rule."},
            {"title": "Apply the chain rule", "goal": "Multiply the pieces.", "result_latex": r"2x\cos(x^2)",
             "first_question": "How does the chain rule combine the two derivatives?",
             "check_question": "Why do we multiply the derivatives?", "safe_hint": "Chain rule: outer' times inner'."},
        ],
    },
    "2x+3=7": {
        "level": 3, "title": "Solve a two-step equation", "final_answer_latex": "x = 2",
        "steps": [
            {"title": "Undo the addition", "goal": "Subtract 3 from both sides.", "result_latex": "2x = 4",
             "first_question": "What can you do to both sides to get rid of the +3?",
             "check_question": "Why must you do it to both sides?", "safe_hint": "Think about the opposite of adding."},
            {"title": "Undo the multiplication", "goal": "Divide by 2.", "result_latex": "x = 2",
             "first_question": "Now how do you get x by itself?",
             "check_question": "Why does dividing work here?", "safe_hint": "The opposite of multiplying."},
        ],
    },
    "2(x+1)+0": {
        "level": 4, "title": "Expand the expression", "final_answer_latex": "2x+2",
        "steps": [
            {"title": "Distribute", "goal": "Distribute 2.", "result_latex": "2x+2",
             "first_question": "What do you get when you distribute the 2?",
             "check_question": "Why does distributing work?", "safe_hint": "Multiply 2 by each term."},
        ],
    },
}


def default_turn(**overrides) -> dict:
    d = {"intent": "on-step", "reply": "Think about it. What do you notice?", "question": "What do you notice?",
         "learner_correct": "n/a", "check_passed": False, "display_title": "", "display_items": [],
         "display_keep": False}
    d.update(overrides)
    return d


class Script:
    """Drives FakeProvider responses. Queue turn responses with .push()."""

    def __init__(self):
        self.turns: deque = deque()
        self.default = default_turn()
        # Phase 2: what the "vision model" reads from any image.
        self.vision: dict | None = {"readable": True, "kind": "math", "latex": r"5\times5", "text": "",
                                    "instruction": "", "note": ""}

    def push(self, *responses: dict | None):
        self.turns.extend(responses)

    def __call__(self, req):
        if req.purpose == "intake":
            msg = req.messages[0]["content"]
            problem = re.search(r"PROBLEM \([^)]*\): (.*)", msg).group(1).strip()
            return PLANS.get(problem, PLANS["2(x+1)+0"])
        if req.purpose == "probe":
            return {"ok": True}
        if req.purpose == "vision":
            return self.vision
        # (turns fall through)
        if self.turns:
            return self.turns.popleft()
        return dict(self.default)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MATHASSISTANT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MATHASSISTANT_KEYRING_SERVICE", "mathassistant-test")
    monkeypatch.delenv("DEV_MODE", raising=False)
    monkeypatch.delenv("ANTHROPIC_DEV_API_KEY", raising=False)
    yield


@pytest.fixture
def script():
    return Script()


@pytest.fixture
def fake(script):
    return FakeProvider(responder=script)


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "data" / "test.sqlite3")


def make_client(storage, provider_factory=None) -> TestClient:
    app = create_app(token=TOKEN, port_getter=lambda: PORT, storage=storage,
                     provider_factory=provider_factory, web_dir=None)
    client = TestClient(app, base_url=BASE)
    client.headers["X-Session-Token"] = TOKEN
    return client


@pytest.fixture
def client(storage, fake):
    c = make_client(storage, lambda: fake)
    # Tutoring requires a verified key; with the fake provider, Test key always passes.
    r = c.post("/api/key/test", json={"provider": "anthropic", "model": "claude-haiku-4-5"})
    assert r.status_code == 200, r.text
    fake.calls.clear()
    return c


def tutor_texts(view: dict) -> list[str]:
    return [e["text"] for e in view["transcript"] if e["role"] == "tutor"]


os.environ.setdefault("MATHASSISTANT_NO_BROWSER", "1")
