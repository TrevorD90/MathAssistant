"""Regression: the 2026-09-28 live session on lim_{x->2}(8-3x+12^2) = 146.

Bugs reproduced here:
1. A correct answer for a later step / the final answer was graded INCORRECT
   against the current step, and the tutor told the learner "your arithmetic
   doesn't match".
2. Equation-shaped step results ("12^2 = 144") never matched a plain answer (144).
3. The leak guard blocked the tutor from echoing values the learner had typed
   (146, 144), producing the same canned hint over and over.
4. Chains ("152-3(2) = 152 - 6 = 146") and prose ("152 - 6 is 146") weren't read.
"""

from __future__ import annotations

import pytest

from conftest import PLANS, default_turn, tutor_texts
from mathassistant.engine.answer_check import Verdict, check_step
from mathassistant.engine.answer_router import candidates, route
from mathassistant.engine.leak_guard import GuardContext, scan, target_from_latex
from mathassistant.engine.solver import solve_latex
from test_tutoring import start, turn

PROBLEM = r"\lim_{x\to2}\left(8-3x+12^2\right)"

# The plan the live model actually produced (from the saved problem).
PLANS[PROBLEM] = {
    "level": 4, "title": "Limit of a polynomial expression", "final_answer_latex": "146",
    "steps": [
        {"title": "Identify the type of function", "goal": "Recognize a polynomial is continuous.", "result_latex": "",
         "first_question": "What kind of function is inside the limit?", "check_question": "Why can we substitute directly?",
         "safe_hint": "Think about whether the graph has any breaks."},
        {"title": "Simplify the constant terms", "goal": "Evaluate 12^2.", "result_latex": "12^2 = 144",
         "first_question": "What is the value of the squared term?", "check_question": "How did you compute it?",
         "safe_hint": "Calculate 12 times 12 to find the squared value."},
        {"title": "Rewrite with simplified constants", "goal": "Combine constants.",
         "result_latex": "8 + 144 - 3x = 152 - 3x", "first_question": "How can you combine the constant terms?",
         "check_question": "Why can you combine 8 and 144?", "safe_hint": "Add the plain numbers together."},
        {"title": "Substitute x = 2", "goal": "Substitute.", "result_latex": "152 - 3(2)",
         "first_question": "What do you get when you put 2 in for x?", "check_question": "Why can you substitute here?",
         "safe_hint": "Replace every x with 2."},
        {"title": "Calculate the final result", "goal": "Finish the arithmetic.", "result_latex": "146",
         "first_question": "What is the final value?", "check_question": "How can you check your result?",
         "safe_hint": "Do the multiplication first, then subtract."},
    ],
}


def _steps():
    return PLANS[PROBLEM]["steps"]


# ------------------------------------------------------------------ unit level

def test_equation_shaped_step_results_accept_plain_values():
    assert check_step("144", "12^2 = 144") == Verdict.CORRECT
    assert check_step("12^2", "12^2 = 144") == Verdict.NOT_SIMPLIFIED
    assert check_step("152-3x", "8 + 144 - 3x = 152 - 3x") == Verdict.CORRECT
    # An unevaluated planned result accepts any equivalent form.
    assert check_step("152-3(2)", "152 - 3(2)") == Verdict.CORRECT
    assert check_step("146", "152 - 3(2)") == Verdict.CORRECT
    # Genuine equations still compare as equations.
    assert check_step("4x=8", "2x = 4") == Verdict.CORRECT


@pytest.mark.parametrize("text, latex, expect_target", [
    ("", "146", "final"),
    ("", "152-3(2)", "later"),
    ("", "152-3(2) = 152 - 6 = 146", "final"),      # chain: last side is the answer
    ("152 - 6 is 146", "", "final"),                  # prose with the answer in it
    ("I already told you, it's 146", "", "final"),
    ("", "144", "current"),
])
def test_router_matches_final_and_later_steps(text, latex, expect_target):
    m = route(candidates(text, latex), 1, _steps(), solve_latex(PROBLEM), PLANS[PROBLEM])
    assert m.verdict == Verdict.CORRECT
    assert m.target == expect_target


def test_router_wrong_answer_still_incorrect_and_prose_never_penalized():
    sol = solve_latex(PROBLEM)
    assert route(candidates("", "147"), 1, _steps(), sol, PLANS[PROBLEM]).verdict == Verdict.INCORRECT
    m = route(candidates("is it 147?", ""), 1, _steps(), sol, PLANS[PROBLEM])
    assert m.from_words and m.verdict != Verdict.CORRECT


def test_guard_lets_tutor_echo_what_the_learner_typed():
    sol = solve_latex(PROBLEM)
    final = target_from_latex("final", "146")
    step = target_from_latex("step", "12^2 = 144")
    assert step.value == 144                      # identity -> its value, not a text-only target
    ctx = GuardContext([final, step], PROBLEM, revealed_latex=["146", "144"])
    assert scan("Yes, 152 - 6 is 146, and 12^2 = 144.", ctx) is None
    # Typing the unfinished arithmetic does NOT unlock the final number.
    ctx2 = GuardContext([final], PROBLEM, revealed_latex=["152-3(2)"])
    assert scan("That gives 146.", ctx2) is not None
    assert sol.kind == "number"


# ------------------------------------------------------------------ engine level

def test_session_replay_correct_answers_never_graded_wrong(client, script, fake):
    view = start(client, PROBLEM)
    pid = view["id"]
    # Step 1 is conceptual; the AI accepts it and (no mistakes) the tutor moves on.
    script.push(default_turn(reply="Right. What is the value of the squared term?",
                             question="What is the value of the squared term?", learner_correct="yes"))
    view = turn(client, pid, text="a polynomial")
    assert view["step_index"] == 1 and view["phase"] == "working"

    # Learner skips ahead and types the substitution (step 4's result): accepted, no AI call.
    fake.calls.clear()
    view = turn(client, pid, latex="152-3(2)")
    assert fake.call_count == 0
    assert view["step_index"] == 4 and view["phase"] == "working"
    assert "worked ahead" in tutor_texts(view)[-1]
    assert all(s["status"] == "done" for s in view["steps"][:4])

    # 146 is the final answer: accepted and the problem is solved. Never "doesn't match".
    view = turn(client, pid, latex="146")
    assert view["status"] == "completed"
    assert "doesn't match" not in " ".join(tutor_texts(view))
    assert tutor_texts(view)[-1] == "Correct. You solved it: $146$."
    assert fake.call_count == 0


def test_wrong_then_right_asks_one_why_question(client, script):
    view = start(client, PROBLEM)
    pid = view["id"]
    script.push(default_turn(reply="Right. What is 12 squared?", question="?", learner_correct="yes"))
    turn(client, pid, text="a polynomial")
    script.push(default_turn(reply="Not quite. Try again.", question="What is 12 squared?"))
    turn(client, pid, latex="124")
    view = turn(client, pid, latex="144")
    assert view["phase"] == "checking"
    assert "How did you compute it?" in tutor_texts(view)[-1]


def test_final_answer_early_in_prose_completes(client, script):
    view = start(client, PROBLEM)
    view = turn(client, view["id"], text="152 - 6 is 146")
    assert view["status"] == "completed"


def test_144_accepted_for_equation_shaped_step(client, script):
    view = start(client, PROBLEM)
    pid = view["id"]
    script.push(default_turn(reply="Right. What is 12 squared?", question="?", learner_correct="yes"))
    turn(client, pid, text="a polynomial")
    view = turn(client, pid, latex="144")
    assert view["step_index"] == 2 and view["phase"] == "working"
    assert view["turn_ai_calls"] == 0