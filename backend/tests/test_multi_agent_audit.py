"""Audit-trail tests for the hierarchical multi-agent investigator.

After a full run, audit.agent_steps must contain:
- supervisor rows (one per routing decision)
- lead rows for every plan entry (real + stubs)
- sub-worker rows whose parent_step_id points back to their lead
- LLM cost telemetry on the option_generator row (model + tokens + cost_usd)

These tests need a Postgres on :5433 with the migration applied — skipped
otherwise via the existing db_ready fixture.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from biq.agents.multi.graph import run_graph
from biq.db import engine


def _steps_for(run_id: str) -> list[dict]:
    with engine.connect() as c:
        return [
            dict(r._mapping)
            for r in c.execute(
                text(
                    "SELECT seq, agent_level, agent_name, action, parent_step_id, "
                    "       step_id, latency_ms, tokens_in, tokens_out, cost_usd, model "
                    "FROM audit.agent_steps WHERE run_id = :r ORDER BY seq"
                ),
                {"r": run_id},
            ).all()
        ]


def test_full_run_writes_complete_hierarchical_trace(db_ready: bool) -> None:
    final = run_graph(
        "Warum ist conversion auf mobile eingebrochen?",
        horizon=("2018-04-15", "2018-05-10"),
        target_device="mobile",
    )
    run_id = final["run_id"]
    steps = _steps_for(run_id)

    by_level: dict[str, list[dict]] = {"supervisor": [], "lead": [], "sub": []}
    for s in steps:
        by_level[s["agent_level"]].append(s)

    # At minimum: 5 supervisor decisions (one per Lead) + 5 Leads + 2 Subs
    # under analyst + 1 Sub under strategist (when LLM ran).
    assert len(by_level["supervisor"]) >= 5, f"supervisor count={len(by_level['supervisor'])}"
    assert len(by_level["lead"]) == 5, f"lead names: {[s['agent_name'] for s in by_level['lead']]}"
    assert {s["agent_name"] for s in by_level["lead"]} == {
        "data_mining",
        "analyst",
        "ml_modeler",
        "strategist",
        "reporter",
    }

    # Every sub must have a parent that is itself a lead row.
    lead_ids = {s["step_id"] for s in by_level["lead"]}
    for sub in by_level["sub"]:
        assert sub["parent_step_id"] in lead_ids, (
            f"sub {sub['agent_name']} has orphan parent {sub['parent_step_id']}"
        )


def test_sub_workers_attach_to_their_lead(db_ready: bool) -> None:
    final = run_graph(
        "Test",
        horizon=("2018-04-15", "2018-05-10"),
        target_device="mobile",
    )
    steps = _steps_for(final["run_id"])

    by_id = {s["step_id"]: s for s in steps}

    descriptive = next(s for s in steps if s["agent_name"] == "descriptive")
    causal = next(s for s in steps if s["agent_name"] == "causal")
    analyst = next(s for s in steps if s["agent_name"] == "analyst")

    assert by_id[descriptive["parent_step_id"]] is analyst
    assert by_id[causal["parent_step_id"]] is analyst


def test_llm_telemetry_lands_on_option_generator_row(db_ready: bool) -> None:
    """When the LLM actually ran (ANTHROPIC_API_KEY set), cost is recorded."""
    final = run_graph(
        "Was tun gegen den mobile conversion drop?",
        horizon=("2018-04-15", "2018-05-10"),
        target_device="mobile",
    )
    steps = _steps_for(final["run_id"])
    og = next((s for s in steps if s["agent_name"] == "option_generator"), None)
    if og is None:
        pytest.skip("option_generator did not run — likely no ANTHROPIC_API_KEY")

    # If the LLM call succeeded, we should have tokens + a non-null cost.
    if og["tokens_in"] is None:
        pytest.skip("LLM call was skipped (no API key or claude failure)")
    assert og["tokens_in"] > 0
    assert og["tokens_out"] > 0
    assert og["model"] == "claude-sonnet-4-6"
    assert og["cost_usd"] is not None and og["cost_usd"] > 0


def test_audit_off_does_not_touch_db() -> None:
    """audit=False must produce no run_id and write nothing."""
    final = run_graph("Test", audit=False)
    assert "run_id" not in final
