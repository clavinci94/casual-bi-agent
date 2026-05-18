"""Tests for the Analyst-Lead and its sub-workers.

Split into:
- Unit tests for the deterministic descriptive sub-worker (no DB, no LLM).
- Integration tests that hit Postgres (skipped via db_ready when DB or
  schemas are missing).
- A causal-marked test that additionally needs the R service on :8765.
"""

from __future__ import annotations

import pytest

from biq.agents.multi.graph import build_graph
from biq.agents.multi.leads.analyst import analyst_node
from biq.agents.multi.state import GlobalState
from biq.agents.multi.sub import descriptive as descriptive_sub
from biq.agents.multi.supervisor import DEFAULT_PLAN

# --- Pure unit tests -----------------------------------------------------


def test_derive_baseline_uses_same_length_window_before_horizon() -> None:
    assert descriptive_sub.derive_baseline("2026-05-15", "2026-05-21") == (
        "2026-05-08",
        "2026-05-14",
    )


def test_derive_baseline_single_day_horizon() -> None:
    assert descriptive_sub.derive_baseline("2026-05-15", "2026-05-15") == (
        "2026-05-14",
        "2026-05-14",
    )


def test_analyst_skips_cleanly_without_horizon() -> None:
    """Without a horizon the Analyst must NOT crash — it returns notes."""
    state: GlobalState = {"question": "Foo"}
    patch = analyst_node(state)
    result = patch["analysis"]
    assert result.findings == []
    assert result.causal_estimates == []
    assert result.method_notes and "no `horizon`" in result.method_notes
    assert patch["completed"] == ["analyst"]


# --- Integration tests (need Postgres) -----------------------------------


def test_analyst_emits_finding_for_simulated_mobile_drop(db_ready: bool) -> None:
    """With the simulator-seeded mobile regression, descriptive must spot it."""
    patch = analyst_node(
        {
            "question": "Warum ist conversion auf mobile eingebrochen?",
            "horizon": ("2018-04-15", "2018-05-10"),
            "target_device": "mobile",
        }
    )
    result = patch["analysis"]
    assert result.findings, f"expected at least one finding; notes={result.method_notes}"
    mobile = [f for f in result.findings if "mobile" in f.title.lower()]
    assert mobile, "expected a mobile-specific finding"
    assert mobile[0].severity in ("medium", "high")
    # Drop should be negative — the simulator regresses mobile v2 down.
    assert "eingebrochen" in mobile[0].title


def test_full_graph_runs_analyst_in_pipeline(db_ready: bool) -> None:
    """End-to-end: supervisor visits analyst between data_mining and ml."""
    graph = build_graph()
    initial: GlobalState = {
        "question": "Test",
        "horizon": ("2018-04-15", "2018-05-10"),
        "target_device": "mobile",
        "plan": list(DEFAULT_PLAN),
        "completed": [],
        "iteration": 0,
    }
    final = graph.invoke(initial)
    assert "analyst" in final["completed"]
    assert final["analysis"].findings, "analyst should produce real findings on seeded DB"


# --- Causal (additionally needs R service on :8765) ----------------------


@pytest.mark.causal
def test_causal_subworker_returns_estimate(db_ready: bool) -> None:
    patch = analyst_node(
        {
            "horizon": ("2018-04-15", "2018-05-10"),
            "target_device": "mobile",
        }
    )
    result = patch["analysis"]
    assert result.causal_estimates, f"expected causal estimate; method_notes={result.method_notes}"
    est = result.causal_estimates[0]
    # The simulated mobile regression is a real, large negative effect.
    assert est.estimate is not None and est.estimate < 0
    assert est.p_value is not None and est.p_value < 0.05
