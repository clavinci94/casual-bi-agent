"""Phase 1 skeleton tests for the hierarchical multi-agent investigator.

No DB and no LLM: this exercise stays in-process so it runs in CI without
fixtures. Real Lead behaviour gets covered in Phase 2 with proper integration
tests against a seeded Postgres.
"""

from __future__ import annotations

from biq.agents.multi.graph import build_graph, run_graph
from biq.agents.multi.state import (
    GlobalState,
    ReportResult,
    StrategyOption,
    StrategyResult,
)
from biq.agents.multi.supervisor import (
    DEFAULT_PLAN,
    MAX_ITERATIONS,
    _next_lead,
    route_from_supervisor,
)


def test_default_plan_runs_every_lead_exactly_once() -> None:
    final = run_graph("Warum ist conversion gestern eingebrochen?", audit=False)
    assert final["completed"] == list(DEFAULT_PLAN)
    # Supervisor was entered once per lead.
    assert final["iteration"] == len(DEFAULT_PLAN)


def test_final_state_carries_report_result() -> None:
    final = run_graph("Test", audit=False)
    assert isinstance(final["report"], ReportResult)
    assert final["report"].headline_de
    assert final["report"].summary_de  # at minimum the question is echoed


def test_strategy_options_propagate_to_reporter() -> None:
    """A pre-filled strategy slot is respected when the strategist is bypassed.

    The strategist Lead now owns the strategy slot and would overwrite a
    seeded value if it ran. So we mark 'strategy' as already completed —
    the supervisor then skips straight to the reporter and the seeded
    options must surface in the manager-facing report.
    """
    graph = build_graph()
    seeded = StrategyResult(
        options=[
            StrategyOption(
                title="Rollback Mobile-Release v2",
                body_de="Letzte Release zurücknehmen, A/B nachfahren.",
                expected_impact_de="Conversion ~+8% innerhalb 24h erwartet.",
                risks_de=["Marketing-Kampagne läuft auf neue UI"],
                effort="medium",
            )
        ],
        risk_level="high",
    )
    initial: GlobalState = {
        "question": "Test",
        "plan": list(DEFAULT_PLAN),
        "completed": ["data_mining", "analyst", "ml", "strategy"],
        "iteration": 4,
        "strategy": seeded,
    }
    final = graph.invoke(initial)
    assert final["report"].risk_level == "high"
    assert len(final["report"].top_options) == 1
    assert final["report"].top_options[0].title.startswith("Rollback")


def test_supervisor_routes_to_next_unfinished_lead() -> None:
    state: GlobalState = {
        "plan": list(DEFAULT_PLAN),
        "completed": ["data_mining", "analyst"],
        "iteration": 3,
    }
    assert _next_lead(state) == "ml"
    assert route_from_supervisor(state) == "ml"


def test_supervisor_falls_through_to_reporter_when_plan_done() -> None:
    state: GlobalState = {
        "plan": list(DEFAULT_PLAN),
        "completed": ["data_mining", "analyst", "ml", "strategy"],
        "iteration": 5,
    }
    assert route_from_supervisor(state) == "reporter"


def test_iteration_cap_forces_reporter() -> None:
    state: GlobalState = {
        "plan": list(DEFAULT_PLAN),
        "completed": [],
        "iteration": MAX_ITERATIONS + 1,
    }
    assert route_from_supervisor(state) == "reporter"
