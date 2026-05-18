"""HTTP API tests for the AI²L (assisted) multi-agent investigator.

POST scenarios validate payload + return 202 — they do NOT wait on the
background run to finish (that would burn a real Claude call per test).
GET scenarios run a pre-tripped budget so the multi-agent graph short-
circuits to the reporter immediately — fast, deterministic, no LLM.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from biq.agents.multi import graph as multi_graph
from biq.agents.multi.budget import RunBudget
from biq.api.app import app

client = TestClient(app)


# --- POST validation -----------------------------------------------------


def test_post_assisted_rejects_short_question() -> None:
    r = client.post("/api/investigations/assisted", json={"question": "hi"})
    assert r.status_code == 422


def test_post_assisted_rejects_partial_horizon() -> None:
    r = client.post(
        "/api/investigations/assisted",
        json={"question": "Wieso ist mobile eingebrochen?", "horizon_start": "2018-04-15"},
    )
    assert r.status_code == 422
    assert "horizon_start and horizon_end" in r.json()["detail"]


def test_post_assisted_rejects_reversed_horizon() -> None:
    r = client.post(
        "/api/investigations/assisted",
        json={
            "question": "Wieso ist mobile eingebrochen?",
            "horizon_start": "2018-05-10",
            "horizon_end": "2018-04-15",
        },
    )
    assert r.status_code == 422


def test_post_assisted_accepts_minimal_payload(db_ready: bool) -> None:
    """POST returns 202 + run_id immediately; we don't wait for completion."""
    r = client.post(
        "/api/investigations/assisted",
        json={"question": "Test investigation"},
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "started"
    assert body["run_id"]
    assert body["poll_url"].endswith(body["run_id"])
    assert body["detail_url"].endswith(body["run_id"])


# --- GET -----------------------------------------------------------------


def test_get_assisted_404_for_unknown_run(db_ready: bool) -> None:
    r = client.get("/api/investigations/assisted/does-not-exist")
    assert r.status_code == 404


def test_get_assisted_returns_full_shape_after_run(db_ready: bool) -> None:
    """Run the multi-agent graph synchronously with a tripped budget so the
    supervisor goes straight to reporter (no LLM cost), then GET the run."""
    tight = RunBudget(max_tokens=10, max_cost_usd=0.01)
    tight.record("synthetic", 100, 100, 1.0)  # pre-trip

    final = multi_graph.run_graph(
        question="API assisted GET smoke test",
        audit=True,
        budget=tight,
    )
    run_id = final["run_id"]

    r = client.get(f"/api/investigations/assisted/{run_id}")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["run_id"] == run_id
    assert body["status"] == "ok"
    assert body["question"] == "API assisted GET smoke test"
    assert body["report"] is not None
    assert body["report"]["headline_de"]
    assert body["report"]["summary_de"]

    # Budget tripped → reporter ran but other Leads were skipped.
    assert any("budget exceeded" in q for q in body["open_questions"])

    # Step trace: exactly one reporter row, no option_generator (budget tripped).
    agents = [s["agent_name"] for s in body["steps"]]
    assert agents.count("reporter") == 1
    assert "option_generator" not in agents

    # Hierarchical attribution: every sub row points at a lead row.
    lead_ids = {s["step_id"] for s in body["steps"] if s["agent_level"] == "lead"}
    for s in body["steps"]:
        if s["agent_level"] == "sub":
            assert s["parent_step_id"] in lead_ids
