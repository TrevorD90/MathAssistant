"""Word problems (added 2026-09-28).

The intake call also returns `math_formulation_latex` (words -> math); SymPy
computes the answer from it, so the model never decides the number (N8).
"""

from __future__ import annotations

import sqlite3

from conftest import PLANS, default_turn, tutor_texts
from mathassistant import migrations
from mathassistant.engine import intent
from mathassistant.storage import Storage
from test_tutoring import turn

APPLES = "Sam has 3 bags with 12 apples in each bag. How many apples does Sam have?"
DOGS = "Maya walks 4 dogs twice a day. How many dog walks does she do in 5 days?"

PLANS[APPLES] = {
    "level": 1, "title": "Apples in bags",
    "final_answer_latex": "35",                       # deliberately wrong: SymPy must override it
    "math_formulation_latex": r"3\times 12",
    "steps": [
        {"title": "Find the groups", "goal": "See 3 groups of 12.", "result_latex": "",
         "first_question": "How many bags are there, and how many apples are in each?",
         "check_question": "Why is this a multiplying problem?", "safe_hint": "Look at the numbers in the story."},
        {"title": "Count all the apples", "goal": "Multiply.", "result_latex": "35",
         "first_question": "How many apples are there in all?",
         "check_question": "How did you find the total?", "safe_hint": "Add 12 three times."},
    ],
}
PLANS[DOGS] = {
    "level": 2, "title": "Dog walks", "final_answer_latex": "40", "math_formulation_latex": r"4\times 2\times 5",
    "steps": [
        {"title": "Walks per day", "goal": "Find walks per day.", "result_latex": "8",
         "first_question": "How many walks happen in one day?", "check_question": "Why?",
         "safe_hint": "Each dog is walked twice."},
        {"title": "Walks in 5 days", "goal": "Multiply by days.", "result_latex": "40",
         "first_question": "How many walks in 5 days?", "check_question": "Why?", "safe_hint": "5 days of that."},
    ],
}


def start_words(client, text):
    r = client.post("/api/problems", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def test_word_problem_starts_and_is_saved_as_words(client):
    view = start_words(client, APPLES)
    assert view["problem_kind"] == "words"
    assert view["problem_latex"] == APPLES
    listing = client.get("/api/problems").json()
    assert listing["in_progress"][0]["problem_kind"] == "words"


def test_sympy_answer_from_formulation_overrides_model(client, storage):
    view = start_words(client, APPLES)
    rec = storage.get_problem(view["id"])
    assert rec.plan["final_answer_latex"] == "36"               # 3 x 12 by SymPy, not the model's 35
    assert rec.plan["steps"][-1]["result_latex"] == "36"        # last step corrected too
    assert rec.solution["kind"] == "number"


def test_answer_with_units_in_words_is_accepted(client, fake):
    view = start_words(client, APPLES)
    fake.calls.clear()
    view = turn(client, view["id"], text="36 apples")
    assert view["status"] == "completed"
    assert fake.call_count == 0


def test_answer_with_units_in_latex_is_accepted(client):
    view = start_words(client, APPLES)
    view = turn(client, view["id"], latex=r"36\text{ apples}")
    assert view["status"] == "completed"


def test_wrong_model_answer_is_not_accepted(client, script):
    view = start_words(client, APPLES)
    script.push(default_turn(reply="Not quite. Try adding 12 three times.", question="How many?"))
    view = turn(client, view["id"], latex="35")
    assert view["status"] == "in_progress"


def test_guard_blocks_the_answer_in_word_problems(client, script):
    view = start_words(client, APPLES)
    script.push(default_turn(reply="There are 36 apples.", question="See?"),
                default_turn(reply="That's thirty-six apples!", question="See?"))
    view = turn(client, view["id"], text="I don't get it")
    joined = " ".join(tutor_texts(view)).lower()
    assert "36" not in joined and "thirty-six" not in joined


def test_problem_words_are_never_off_topic(client, fake):
    view = start_words(client, DOGS)
    fake.calls.clear()
    turn(client, view["id"], text="do the dogs count separately?")
    assert fake.call_count == 1                   # went to the AI, not a canned redirect
    vocab = intent.problem_vocabulary(DOGS)
    assert not intent.is_obviously_off_topic("do you like dogs", vocab)
    assert intent.is_obviously_off_topic("what's your favorite movie", vocab)


def test_word_problem_without_formulation_falls_back_to_model_answer(client, script, storage):
    text = "Explain why the sum of two even numbers is even."
    PLANS[text] = {
        "level": 3, "title": "Even sums", "final_answer_latex": r"\text{always even}", "math_formulation_latex": "",
        "steps": [{"title": "Write evens", "goal": "Use 2a and 2b.", "result_latex": "",
                   "first_question": "How can you write any even number?", "check_question": "Why?",
                   "safe_hint": "Every even number is 2 times something."}],
    }
    view = start_words(client, text)
    rec = storage.get_problem(view["id"])
    assert rec.solution["kind"] == "none"
    assert rec.plan["final_answer_latex"] == r"\text{always even}"


def test_empty_problem_rejected(client):
    r = client.post("/api/problems", json={"text": "   "})
    assert r.status_code == 400


def test_migration_v1_to_v2_keeps_existing_problems(tmp_path):
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("BEGIN")
    for stmt in (s.strip() for s in migrations.MIGRATIONS[0].split(";")):
        if stmt:
            conn.execute(stmt)
    conn.execute("PRAGMA user_version = 1")
    conn.execute("COMMIT")
    conn.execute(
        "INSERT INTO problems (id, title, problem_latex, level, plan_json, solution_json, state_json, "
        "transcript_json, status, created_at, updated_at) VALUES "
        "('old1', 'Old', '5\\times5', 1, '{\"steps\": []}', '{}', '{}', '[]', 'in_progress', 't', 't')")
    conn.close()

    st = Storage(path)                                   # runs v2
    rec = st.get_problem("old1")
    assert rec is not None and rec.problem_kind == "math" and rec.title == "Old"
    with sqlite3.connect(path) as c:
        assert migrations.current_version(c) == len(migrations.MIGRATIONS)


MONEY = "Sam has $5 and buys a toy for $2. How much money does Sam have left?"
PLANS[MONEY] = {
    "level": 1, "title": "Money left", "final_answer_latex": "3", "math_formulation_latex": "5-2",
    "steps": [{"title": "Take away the cost", "goal": "Subtract.", "result_latex": "3",
               "first_question": "How much did the toy cost?", "check_question": "Why subtract?",
               "safe_hint": "Start with the money Sam had."}],
}


def test_money_is_not_math_markup():
    from mathassistant.engine.leak_guard import extract_segments

    assert extract_segments("Sam has $5 and buys a toy for $2.") == []
    assert extract_segments(r"So $2x\cos(x^2)$ it is") == [r"2x\cos(x^2)"]


def test_money_word_problem_answer_with_dollar_sign(client):
    view = start_words(client, MONEY)
    view = turn(client, view["id"], text="$3")
    assert view["status"] == "completed"
