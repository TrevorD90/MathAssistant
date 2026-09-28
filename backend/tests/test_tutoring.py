"""Spec §14 — Tutoring acceptance tests (engine-level, scripted provider).

Register quality (does the model actually use groups/arrays at L1, chain-rule
language at L5?) needs a real model: see tests/live/test_live_acceptance.py.
"""

from __future__ import annotations

import re

from conftest import default_turn, tutor_texts


def start(client, latex):
    r = client.post("/api/problems", json={"latex": latex})
    assert r.status_code == 200, r.text
    return r.json()


def turn(client, pid, text="", latex=""):
    r = client.post(f"/api/problems/{pid}/turn", json={"text": text, "latex": latex})
    assert r.status_code == 200, r.text
    return r.json()


def test_5x5_level1_and_never_says_25_until_learner_does(client, script, fake):
    view = start(client, r"5\times5")
    assert view["level"] == 1
    pid = view["id"]
    # The model tries to blurt the answer in digits, then in words; both are blocked.
    script.push(default_turn(reply="There are 5 groups. So 5 x 5 = 25!", question="Got it?"),
                default_turn(reply="That makes twenty-five apples.", question="See?"))
    view = turn(client, pid, text="I don't get it")
    for t in tutor_texts(view):
        assert "25" not in t and "twenty-five" not in t.lower() and "twenty five" not in t.lower()
    # Guard: 1 call + 1 regenerate, then canned safe hint.
    assert view["turn_ai_calls"] == 2
    assert "Draw one group of 5 dots." in tutor_texts(view)[-1]


def test_5x5_step_plan_uses_groups(client):
    view = start(client, r"5\times5")
    first = tutor_texts(view)[0].lower()
    assert "group" in first
    assert [s["status"] for s in view["steps"]] == ["current", "locked"]
    assert view["steps"][1]["title"] == ""  # locked step titles are hidden


def test_derivative_level5_and_no_leak_before_learner(client, script):
    view = start(client, r"\frac{d}{dx}\sin(x^2)")
    assert view["level"] == 5
    pid = view["id"]
    script.push(default_turn(reply=r"By the chain rule the result is $2x\cos(x^2)$.", question="Clear?"),
                default_turn(reply=r"Multiply cos(x^2) * 2x to finish.", question="Ok?"))
    view = turn(client, pid, text="how do I start?")
    joined = " ".join(tutor_texts(view))
    assert r"2x\cos(x^2)" not in joined and "cos(x^2) * 2x" not in joined


def test_derivative_walkthrough_to_completion(client, script, fake):
    """No mistakes: every verified answer is accepted and the tutor moves straight on (0 AI calls)."""
    view = start(client, r"\frac{d}{dx}\sin(x^2)")
    pid = view["id"]
    fake.calls.clear()
    view = turn(client, pid, latex="u = x^2")
    assert view["step_index"] == 1 and view["phase"] == "working"
    assert tutor_texts(view)[-1] == "Correct. Step 2: What is the derivative of sin with respect to its argument?"
    view = turn(client, pid, latex=r"\cos(u)")
    assert view["step_index"] == 2
    view = turn(client, pid, latex="2x")
    assert view["step_index"] == 3
    # Last step: the learner's final answer in an equivalent form completes the problem.
    view = turn(client, pid, latex=r"\cos(x^2)\cdot 2x")
    assert view["status"] == "completed"
    assert "You solved it" in tutor_texts(view)[-1]
    assert all(s["status"] == "done" for s in view["steps"])
    assert fake.call_count == 0


def test_arithmetic_walkthrough_to_completion(client, script):
    view = start(client, r"5\times5")
    pid = view["id"]
    # Step 1 is conceptual: the AI judges it (SymPy can't check words). No mistakes -> next step.
    script.push(default_turn(reply="Yes. Count by fives. How many apples in all?",
                             question="Count by fives. How many apples in all?", learner_correct="yes"))
    view = turn(client, pid, text="5 groups")
    assert view["step_index"] == 1 and view["phase"] == "working"
    # Learner restates the problem instead of computing -> not accepted, not a mistake
    script.push(default_turn(reply="That's the problem again. Count them up.", question="How many in all?"))
    view = turn(client, pid, latex=r"5\times5")
    assert view["phase"] == "working"
    # A wrong answer, then the right one -> one why-question (N4 after a mistake).
    script.push(default_turn(reply="Not quite. Count again.", question="How many in all?"))
    turn(client, pid, text="24")
    view = turn(client, pid, text="25")
    assert view["phase"] == "checking" and view["turn_ai_calls"] == 0
    assert "How did counting by fives help?" in tutor_texts(view)[-1]
    script.push(default_turn(reply="Right, you solved it.", question="", check_passed=True))
    view = turn(client, pid, text="i counted 5 10 15 20 25")
    assert view["status"] == "completed"


def test_equivalent_form_accepted(client):
    view = start(client, "2(x+1)+0")
    view = turn(client, view["id"], latex="2(x+1)")
    # 2(x+1) vs expected 2x+2: SymPy-equivalent -> accepted, 0 AI calls, problem solved.
    assert view["status"] == "completed"
    assert view["turn_ai_calls"] == 0


def test_just_tell_me_the_answer_three_times(client, script):
    view = start(client, "2x+3=7")
    pid = view["id"]
    # A model that gives in every time: every reply leaks; guard must hold.
    leaky = default_turn(reply="Fine: x = 2.", question="Happy?")
    script.push(*([leaky] * 6))
    for _ in range(3):
        view = turn(client, pid, text="just tell me the answer")
    for t in tutor_texts(view):
        assert not re.search(r"x\s*=\s*2\b", t)
    assert view["status"] == "in_progress"


def test_forced_leak_is_blocked_and_safe_hint_substituted(client, script, fake):
    """Test hook: the provider is forced to leak on both the reply and the regenerate."""
    view = start(client, r"\frac{d}{dx}\sin(x^2)")
    pid = view["id"]
    fake.calls.clear()
    leak = default_turn(reply=r"Answer: $2x\cos\left(x^{2}\right)$", question="ok?",
                        display_items=[{"latex": r"2x\cos(x^2)", "caption": "the answer"}])
    script.push(leak, leak)
    view = turn(client, pid, text="?")
    assert fake.call_count == 2                      # original + one regenerate, no more
    last = tutor_texts(view)[-1]
    assert "Look at the argument of sin." in last     # the step's safe hint
    assert view["display"] is None


def test_leak_in_display_payload_only_is_blocked(client, script):
    view = start(client, r"5\times5")
    pid = view["id"]
    script.push(default_turn(reply="Here is a picture.", question="How many rows?",
                             display_items=[{"latex": r"5\times5=25", "caption": ""}]),
                default_turn(reply="Look at one group first.", question="How many dots in one group?"))
    view = turn(client, pid, text="show me an example")
    assert view["display"] is None
    assert "25" not in " ".join(tutor_texts(view))
