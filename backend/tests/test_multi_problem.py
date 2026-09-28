"""A worksheet with several problems (2026-09-28).

One vision call lists every problem; the learner picks one to start with, and
the others can be saved to "Up next" (no AI cost until started).
"""

from __future__ import annotations

import base64

from mathassistant.providers.anthropic_provider import _probe_png

B64 = base64.b64encode(_probe_png()).decode()

WORKSHEET = {"readable": True, "note": "", "problems": [
    {"label": "1", "kind": "math", "latex": "2x+3=7", "text": "", "instruction": "Solve"},
    {"label": "2", "kind": "math", "latex": r"\frac{d}{dx}\sin(x^2)", "text": "", "instruction": ""},
    {"label": "3", "kind": "words", "latex": "", "instruction": "",
     "text": "Sam has 3 bags with 12 apples in each bag. How many apples does Sam have?"},
    {"label": "4", "kind": "math", "latex": "", "text": "", "instruction": ""},          # empty -> dropped
    {"label": "5", "kind": "math", "latex": "", "text": "x + 1 = 4", "instruction": ""},  # text in wrong field
]}


def extract(client):
    r = client.post("/api/extract", json={"image_base64": B64, "media_type": "image/png"})
    assert r.status_code == 200, r.text
    return r.json()


def test_all_problems_listed_with_one_call(client, script, fake):
    script.vision = WORKSHEET
    body = extract(client)
    assert fake.call_count == 1
    labels = [p["label"] for p in body["problems"]]
    assert labels == ["1", "2", "3", "5"]
    assert body["problems"][0]["instruction"] == "Solve"
    assert body["problems"][3]["kind"] == "words"          # usable, re-labelled


def test_list_capped_at_20(client, script):
    script.vision = {"readable": True, "note": "", "problems": [
        {"label": str(i), "kind": "math", "latex": f"{i}+1", "text": "", "instruction": ""} for i in range(30)]}
    assert len(extract(client)["problems"]) == 20


def test_pick_one_and_queue_the_rest(client, script, fake):
    script.vision = WORKSHEET
    body = extract(client)
    chosen, rest = body["problems"][1], [p for i, p in enumerate(body["problems"]) if i != 1]
    fake.calls.clear()
    r = client.post("/api/queue", json={"items": rest, "source": "worksheet.pdf"})
    assert r.json()["added"] == 3
    assert fake.call_count == 0                                  # saving costs nothing
    view = client.post("/api/problems", json={"latex": chosen["latex"],
                                              "extraction_ids": [body["extraction_id"]]}).json()
    assert view["problem_latex"] == chosen["latex"]
    listing = client.get("/api/problems").json()
    assert [q["label"] for q in listing["up_next"]] == ["1", "3", "5"]
    assert [p["id"] for p in listing["in_progress"]] == [view["id"]]


def test_starting_from_up_next_removes_it(client, script):
    client.post("/api/queue", json={"items": [
        {"kind": "math", "latex": "2x+3=7", "label": "1"},
        {"kind": "words", "text": "Sam has 3 bags with 12 apples in each bag. How many apples does Sam have?",
         "label": "2"}]})
    queued = client.get("/api/problems").json()["up_next"]
    first = queued[0]
    view = client.post("/api/problems", json={"latex": first["problem_text"], "queued_id": first["id"]}).json()
    assert view["problem_latex"] == "2x+3=7"
    left = client.get("/api/problems").json()["up_next"]
    assert [q["label"] for q in left] == ["2"]


def test_failed_start_keeps_the_queued_problem(client, script):
    client.post("/api/queue", json={"items": [{"kind": "math", "latex": "2x+3=7", "label": "1"}]})
    q = client.get("/api/problems").json()["up_next"][0]
    r = client.post("/api/problems", json={"latex": "", "queued_id": q["id"]})     # empty -> error
    assert r.status_code == 400
    assert len(client.get("/api/problems").json()["up_next"]) == 1


def test_delete_queued_and_delete_all(client):
    client.post("/api/queue", json={"items": [{"kind": "math", "latex": "1+1"}, {"kind": "math", "latex": "2+2"}]})
    q = client.get("/api/problems").json()["up_next"]
    assert client.delete(f"/api/queue/{q[0]['id']}").status_code == 200
    assert client.delete("/api/queue/nope").status_code == 404
    assert len(client.get("/api/problems").json()["up_next"]) == 1
    client.delete("/api/problems")
    assert client.get("/api/problems").json()["up_next"] == []


def test_queue_rejects_bad_kind_and_skips_empty(client):
    assert client.post("/api/queue", json={"items": [{"kind": "poem", "text": "x"}]}).status_code == 422
    r = client.post("/api/queue", json={"items": [{"kind": "math", "latex": "  "}, {"kind": "math", "latex": "3+4"}]})
    assert r.json()["added"] == 1


def test_multi_page_usage_counted_on_start(client, script):
    script.vision = WORKSHEET
    a = extract(client)["extraction_id"]
    b = extract(client)["extraction_id"]
    view = client.post("/api/problems", json={"latex": "2x+3=7", "extraction_ids": [a, b]}).json()
    assert view["usage"]["ai_calls"] == 3                        # 2 page reads + intake
