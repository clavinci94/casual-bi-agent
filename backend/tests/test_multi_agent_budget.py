"""Tests for the per-run token + cost budget.

Hermetic: nothing here calls Claude. The integration scenarios pre-trip a
RunBudget and assert the supervisor short-circuits the graph to the reporter.
"""

from __future__ import annotations

from biq.agents.multi.budget import (
    RunBudget,
    budget_exceeded,
    current_budget,
    record_llm_usage,
    reset_budget,
    set_budget,
)
from biq.agents.multi.graph import run_graph

# --- Unit: RunBudget accounting -----------------------------------------


def test_record_accumulates_tokens_and_cost() -> None:
    b = RunBudget(max_tokens=10_000, max_cost_usd=1.0)
    b.record("option_generator", 1000, 500, 0.025)
    b.record("option_generator", 200, 300, 0.010)
    assert b.used_tokens == 2000
    assert round(b.used_cost_usd, 4) == 0.0350
    assert b.exceeded_reason is None


def test_record_trips_on_token_overrun() -> None:
    b = RunBudget(max_tokens=100, max_cost_usd=999.0)
    b.record("option_generator", 80, 30, 0.001)
    assert b.exceeded_reason is not None
    assert "token budget exceeded" in b.exceeded_reason


def test_record_trips_on_cost_overrun() -> None:
    b = RunBudget(max_tokens=1_000_000, max_cost_usd=0.05)
    b.record("option_generator", 10, 10, 0.10)
    assert b.exceeded_reason is not None
    assert "cost budget exceeded" in b.exceeded_reason


def test_reason_is_sticky() -> None:
    """Once set, the reason must not be overwritten by later usage."""
    b = RunBudget(max_tokens=10, max_cost_usd=10.0)
    b.record("a", 20, 0, 0.0)
    first = b.exceeded_reason
    assert first is not None
    b.record("b", 5, 5, 0.0)
    assert b.exceeded_reason == first


def test_record_handles_missing_telemetry() -> None:
    """Deterministic sub-workers report no tokens — record must accept None."""
    b = RunBudget(max_tokens=1000, max_cost_usd=1.0)
    b.record("descriptive", None, None, None)
    assert b.used_tokens == 0
    assert b.used_cost_usd == 0.0
    assert b.exceeded_reason is None


# --- Contextvar wiring --------------------------------------------------


def test_record_llm_usage_is_noop_without_budget() -> None:
    assert current_budget() is None
    record_llm_usage("x", 1000, 1000, 0.5)  # must not raise


def test_set_budget_and_budget_exceeded() -> None:
    b = RunBudget(max_tokens=5, max_cost_usd=999.0)
    token = set_budget(b)
    try:
        assert budget_exceeded() is None
        record_llm_usage("agent", 10, 0, 0.0)
        assert budget_exceeded() is not None
        assert "token budget exceeded" in budget_exceeded()
    finally:
        reset_budget(token)
    assert current_budget() is None


# --- Integration: graph short-circuit ----------------------------------


def test_graph_short_circuits_to_reporter_when_budget_already_exceeded() -> None:
    """Pre-tripped budget → supervisor skips every Lead, only reporter runs."""
    budget = RunBudget(max_tokens=10, max_cost_usd=0.01)
    budget.record("synthetic", 100, 100, 0.5)  # immediately over
    assert budget.exceeded_reason is not None

    final = run_graph("Test", audit=False, budget=budget)

    # The only Lead that should be completed is the reporter.
    assert final["completed"] == ["reporter"]

    # The reason must surface in open_questions so the manager-facing report
    # can explain *why* the investigation stopped early.
    open_qs = final.get("open_questions") or []
    assert any("budget exceeded" in q for q in open_qs), open_qs


def test_graph_runs_full_plan_when_budget_is_generous() -> None:
    """Sanity: with plenty of budget the existing skeleton path is unaffected."""
    budget = RunBudget(max_tokens=10_000_000, max_cost_usd=999.0)
    final = run_graph("Test", audit=False, budget=budget)
    assert final["completed"] == [
        "data_mining",
        "analyst",
        "ml",
        "strategy",
        "reporter",
    ]
