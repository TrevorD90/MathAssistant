"""Spec §14 — Saved problems (+ migrations)."""

from __future__ import annotations

import sqlite3

from conftest import make_client
from mathassistant import migrations
from mathassistant.storage import Storage
from test_tutoring import start, turn


def test_close_and_reopen_resumes_at_same_step(client, storage, fake, tmp_path):
    view = start(client, "2x+3=7")
    pid = view["id"]
    turn(client, pid, latex="2x=4")                      # step 1 correct -> checking phase
    client.close()

    # "Restart the app": fresh Storage + app on the same database file.
    storage2 = Storage(storage.path)
    fake.calls.clear()
    client2 = make_client(storage2, lambda: fake)
    listing = client2.get("/api/problems").json()
    assert [p["id"] for p in listing["in_progress"]] == [pid]
    resumed = client2.get(f"/api/problems/{pid}").json()
    assert resumed["step_index"] == 0 and resumed["phase"] == "checking"
    assert resumed["current_question"] == "Why must you do it to both sides?"
    assert fake.call_count == 0


def test_completed_problem_listed_under_completed(client, script):
    from conftest import default_turn

    view = start(client, "2(x+1)+0")
    turn(client, view["id"], latex="2x+2")
    script.push(default_turn(reply="Right. Done.", question="", check_passed=True))
    turn(client, view["id"], text="each term gets multiplied by 2")
    listing = client.get("/api/problems").json()
    assert [p["id"] for p in listing["completed"]] == [view["id"]]
    assert listing["in_progress"] == []


def test_delete_single_problem(client):
    a = start(client, "2x+3=7")["id"]
    b = start(client, r"5\times5")["id"]
    assert client.delete(f"/api/problems/{a}").status_code == 200
    ids = [p["id"] for p in client.get("/api/problems").json()["in_progress"]]
    assert ids == [b]
    assert client.get(f"/api/problems/{a}").status_code == 404


def test_delete_all_problems(client, storage):
    start(client, "2x+3=7")
    start(client, r"5\times5")
    r = client.delete("/api/problems")
    assert r.json()["deleted"] == 2
    with sqlite3.connect(storage.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM problems").fetchone()[0] == 0


def test_migrations_are_versioned_and_idempotent(tmp_path):
    path = tmp_path / "m.sqlite3"
    Storage(path)
    Storage(path)  # second open must not re-run or fail
    with sqlite3.connect(path) as conn:
        assert migrations.current_version(conn) == len(migrations.MIGRATIONS)


def test_newer_schema_is_not_touched(tmp_path):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version = 99")
    try:
        Storage(path)
        raised = False
    except RuntimeError:
        raised = True
    assert raised
