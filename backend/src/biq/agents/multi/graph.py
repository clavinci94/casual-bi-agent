"""LangGraph wiring for the hierarchical multi-agent investigator.

Flow:

    START -> supervisor -> {data_mining | analyst | ml | strategy | reporter}
              ^                |
              └────────────────┘   (each lead returns control to supervisor)
                                 reporter -> END

Current lead status:
- analyst:    real (kpi + R-causal sub-workers; multi/leads/analyst.py)
- strategist: real (LLM option generator; multi/leads/strategist.py)
- reporter:   real (LLM synthesizer + deterministic placeholder fallback;
              multi/leads/reporter.py)
- data_mining, ml: stubs in this module — real Leads land in Phase 3.

run_graph() opens the audit + budget contextvars so leads and sub-workers
can find them through `multi.audit` / `multi.budget` helpers without
plumbing extra args through every signature.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from biq.agents.multi import audit as ma_audit
from biq.agents.multi import budget as ma_budget
from biq.agents.multi.audit import audit_lead
from biq.agents.multi.budget import RunBudget
from biq.agents.multi.leads.analyst import analyst_node
from biq.agents.multi.leads.reporter import reporter_node
from biq.agents.multi.leads.strategist import strategist_node
from biq.agents.multi.state import (
    DataMiningResult,
    GlobalState,
    MLResult,
)
from biq.agents.multi.supervisor import (
    DEFAULT_PLAN,
    mark_completed,
    route_from_supervisor,
    supervisor_node,
)
from biq.audit import run_context


def data_mining_node(state: GlobalState) -> dict[str, Any]:
    with audit_lead("data_mining", "stub", input={}) as tel:
        tel["output"] = {"stub": True}
        return {
            "data_mining": state.get("data_mining") or DataMiningResult(),
            **mark_completed(state, "data_mining"),
        }


def ml_node(state: GlobalState) -> dict[str, Any]:
    with audit_lead("ml_modeler", "stub", input={}) as tel:
        tel["output"] = {"stub": True}
        return {
            "ml": state.get("ml") or MLResult(),
            **mark_completed(state, "ml"),
        }


def build_graph():
    g = StateGraph(GlobalState)

    g.add_node("supervisor", supervisor_node)
    g.add_node("data_mining", data_mining_node)
    g.add_node("analyst", analyst_node)
    g.add_node("ml", ml_node)
    g.add_node("strategy", strategist_node)
    g.add_node("reporter", reporter_node)

    g.add_edge(START, "supervisor")
    g.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "data_mining": "data_mining",
            "analyst": "analyst",
            "ml": "ml",
            "strategy": "strategy",
            "reporter": "reporter",
        },
    )
    # Every lead hands control back to the supervisor for the next decision.
    for lead in ("data_mining", "analyst", "ml", "strategy"):
        g.add_edge(lead, "supervisor")
    g.add_edge("reporter", END)

    return g.compile()


def run_graph(
    question: str,
    horizon: tuple[str, str] | None = None,
    target_kpi: str | None = None,
    target_device: str | None = None,
    audit: bool = True,
    budget: RunBudget | None = None,
    run_id: str | None = None,
    trigger: str = "multi_agent",
) -> GlobalState:
    """Invoke the multi-agent graph end-to-end. Returns the final state.

    When `audit=True` (default) every Lead + Sub-Worker writes itself into
    audit.agent_steps. If `run_id` is given the helper *attaches* to that
    pre-existing audit.agent_runs row (used by the async API layer, which
    needs to return the run_id synchronously to the client). Otherwise a
    fresh row is opened. `audit=False` skips the DB entirely.

    `budget` defaults to the per-run caps from biq.config.settings. Pass a
    custom RunBudget to enforce tighter limits (tests, expensive tenants).
    When the budget is exceeded mid-run, the supervisor short-circuits to
    the reporter and the open_questions list explains why.
    """
    if budget is None:
        budget = ma_budget.budget_for_settings()

    graph = build_graph()
    initial: GlobalState = {
        "question": question,
        "plan": list(DEFAULT_PLAN),
        "completed": [],
        "iteration": 0,
    }
    if horizon is not None:
        initial["horizon"] = horizon
    if target_kpi is not None:
        initial["target_kpi"] = target_kpi
    if target_device is not None:
        initial["target_device"] = target_device

    budget_token = ma_budget.set_budget(budget)
    try:
        if not audit:
            return graph.invoke(initial)

        with run_context(trigger=trigger, prompt=question, run_id=run_id) as ctx:
            initial["run_id"] = ctx.run_id
            ctx_token = ma_audit.set_context(ctx)
            try:
                return graph.invoke(initial)
            finally:
                ma_audit.reset_context(ctx_token)
    finally:
        ma_budget.reset_budget(budget_token)
