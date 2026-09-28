"""Spec §14 — Staying on task, Display box, Cost."""

from __future__ import annotations

from conftest import default_turn, tutor_texts
from test_tutoring import start, turn


# ------------------------------------------------------------------ on task

def test_favorite_movie_redirect_with_zero_ai_calls(client, fake):
    view = start(client, r"\frac{d}{dx}\sin(x^2)")
    fake.calls.clear()
    view = turn(client, view["id"], text="what's your favorite movie")
    assert fake.call_count == 0
    reply = tutor_texts(view)[-1]
    assert reply.startswith("That's not about this problem.")
    assert "Which function sits inside the sine?" in reply   # current question repeated
    assert reply.count(".") <= 3                              # short, one redirect line + question


def test_uncertain_message_goes_to_ai(client, fake, script):
    view = start(client, r"5\times5")
    fake.calls.clear()
    turn(client, view["id"], text="hmm I am not sure")
    assert fake.call_count == 1


def test_model_off_topic_label_does_not_change_state(client, script):
    view = start(client, r"5\times5")
    script.push(default_turn(intent="off-topic", reply="That's not about this problem. How many groups?",
                             question="How many groups?", check_passed=True, learner_correct="yes"))
    after = turn(client, view["id"], text="are there any good books about space")
    assert after["step_index"] == 0 and after["phase"] == "working"


# ------------------------------------------------------------------ display

EXAMPLE = [{"latex": r"3\times4", "caption": "3 groups of 4"}]


def test_display_shown_when_allowed_and_wiped_on_correct_answer(client, script):
    view = start(client, "2x+3=7")
    pid = view["id"]
    # First turn on a new step: display allowed (introducing a step).
    script.push(default_turn(reply="Here's a similar one.", question="What do you subtract?",
                             display_title="Similar", display_items=[{"latex": "3y+1=10", "caption": "similar"}]))
    view = turn(client, pid, text="where do I start?")
    assert view["display"] and view["display"]["items"][0]["latex"] == "3y+1=10"
    # Correct step answer -> wiped (0 AI calls) and the tutor moves on.
    view = turn(client, pid, latex="2x=4")
    assert view["display"] is None
    assert [s["status"] for s in view["steps"]] == ["done", "current"]


def test_display_wiped_on_step_advance_and_steps_persist(client, script):
    view = start(client, "2x+3=7")
    pid = view["id"]
    turn(client, pid, latex="2x=10")        # a mistake first, so a check question follows
    turn(client, pid, latex="2x=4")
    script.push(default_turn(reply="Right. Now how do you get x by itself?", question="How do you get x alone?",
                             check_passed=True, display_keep=True))
    view = turn(client, pid, text="to keep it balanced")
    assert view["step_index"] == 1
    assert view["display"] is None
    assert [s["status"] for s in view["steps"]] == ["done", "current"]
    assert view["steps"][0]["title"] == "Undo the addition"


def test_display_gated_until_second_wrong_attempt(client, script):
    view = start(client, "2x+3=7")
    pid = view["id"]
    # Turn 1 (step just started) — model sends nothing.
    turn(client, pid, text="hmm what")
    # Wrong attempt 1: payload not allowed -> dropped.
    script.push(default_turn(reply="Not quite.", question="Try again?", display_items=EXAMPLE))
    view = turn(client, pid, latex="2x=10")
    assert view["display"] is None
    # Wrong attempt 2: allowed.
    script.push(default_turn(reply="Here's a similar one.", question="Try again?", display_items=EXAMPLE))
    view = turn(client, pid, latex="2x=11")
    assert view["display"] is not None


def test_display_wiped_on_new_problem(client, script):
    view = start(client, "2x+3=7")
    script.push(default_turn(reply="Similar:", question="?", display_items=EXAMPLE))
    view = turn(client, view["id"], text="example please")
    assert view["display"] is not None
    new = start(client, r"5\times5")
    assert new["display"] is None


def test_malformed_payload_leaves_box_empty(client, script):
    view = start(client, "2x+3=7")
    bad = default_turn(reply="See the panel.", question="?", display_items=[{"latex": "", "caption": "x"}])
    script.push(bad)
    view = turn(client, view["id"], text="show me an example")
    assert view["display"] is None


def test_malformed_ai_response_gives_safe_hint_and_notice(client, script):
    view = start(client, "2x+3=7")
    script.push(None, None)
    view = turn(client, view["id"], text="hmm")
    assert "opposite of adding" in tutor_texts(view)[-1]
    view = turn(client, view["id"], text="hmm")
    assert view["notice"] and "tested model" in view["notice"]


# ------------------------------------------------------------------ cost

def test_normal_turn_makes_exactly_one_ai_call(client, fake):
    view = start(client, "2x+3=7")
    fake.calls.clear()
    view = turn(client, view["id"], latex="2x=10")   # wrong answer -> hint turn
    assert fake.call_count == 1
    assert view["turn_ai_calls"] == 1


def test_intake_is_one_ai_call(client, fake):
    start(client, r"\frac{d}{dx}\sin(x^2)")
    assert fake.call_count == 1
    assert fake.calls[0].purpose == "intake"


def test_turn_context_is_compact(client, fake):
    view = start(client, "2x+3=7")
    for i in range(10):
        turn(client, view["id"], text=f"hmm number {i + 10}?")
    last = fake.calls[-1]
    content = last.messages[0]["content"]
    assert len(last.messages) == 1
    assert "hmm number 10?" not in content         # old turns not sent
    assert "hmm number 19?" in content


def test_resume_makes_zero_ai_calls(client, fake):
    view = start(client, "2x+3=7")
    fake.calls.clear()
    r = client.get(f"/api/problems/{view['id']}")
    assert r.status_code == 200
    assert fake.call_count == 0


def test_usage_meter_tracks_tokens(client):
    view = start(client, "2x+3=7")
    assert view["usage"]["ai_calls"] == 1
    assert view["usage"]["tokens_in"] > 0
