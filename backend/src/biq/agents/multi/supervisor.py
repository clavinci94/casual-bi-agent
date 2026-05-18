"""Supervisor node for the hierarchical multi-agent investigator.

AI²L framing: the Supervisor decides *which proposals* to surface to the
manager, not what action the business takes. Finalization always produces a
ReportResult — never an executed change.

The router is *deterministic*: it walks the default plan
data_mining → analyst → ml → strategy → reporter and stops when every
required Lead has written its slot. An LLM-driven router (Supervisor that
chooses Leads based on the question + partial state) is a future option;
the deterministic baseline keeps cost predictable and the graph testable
without an API key.
"""

from __future__ import annotations

from typing import Any

from biq.agents.multi.audit import audit_supervisor
from biq.agents.multi.budget import budget_exceeded
from biq.agents.multi.state import GlobalState, LeadName

# Order matters: every step earlier than `reporter` produces an evidence
# slot the reporter then condenses. Reporter must come last.
DEFAULT_PLAN: list[LeadName] = ["data_mining", "analyst", "ml", "strategy", "reporter"]

# Hard ceiling so a misbehaving router can't loop forever.
MAX_ITERATIONS = 12


def _next_lead(state: GlobalState) -> LeadName | None:
    """Pick the next un-completed Lead from the plan (or None when done)."""
    plan = state.get("plan") or DEFAULT_PLAN
    done = set(state.get("completed") or [])
    for lead in plan:
        if lead not in done:
            return lead
    return None


def supervisor_node(state: GlobalState) -> dict[str, Any]:
    """Decide next Lead, or finalize. Returns a state patch.

    The actual *routing* (which graph edge to follow) happens in
    `route_from_supervisor` — this node just records the decision on
    the state so it's auditable and the conditional edge can read it.

    Two short-circuit conditions force routing straight to the reporter:
    1. Iteration cap reached (defence against router misbehaviour).
    2. Run budget exceeded (token or USD — set by biq.config.settings).
    Either case appends an `open_questions` entry so the manager-facing
    report explains *why* the investigation stopped early.
    """
    iteration = state.get("iteration", 0) + 1
    plan = state.get("plan") or DEFAULT_PLAN
    completed = list(state.get("completed") or [])
    cap_hit = iteration > MAX_ITERATIONS
    budget_reason = budget_exceeded()

    with audit_supervisor(
        action="route",
        input={
            "iteration": iteration,
            "completed": completed,
            "cap_hit": cap_hit,
            "budget_exceeded": bool(budget_reason),
        },
    ) as tel:
        if cap_hit or budget_reason:
            reason = (
                f"Iteration cap ({MAX_ITERATIONS}) reached before plan finished"
                if cap_hit
                else budget_reason
            )
            tel["output"] = {
                "decision": "force_reporter",
                "reason": "iteration_cap" if cap_hit else "budget_exceeded",
                "detail": reason,
            }
            return {
                "iteration": iteration,
                "plan": plan,
                "open_questions": (state.get("open_questions") or []) + [reason],
            }

        next_lead = next((lead for lead in plan if lead not in completed), None)
        tel["output"] = {"decision": next_lead or "finalize"}

    return {
        "iteration": iteration,
        "plan": plan,
    }


def route_from_supervisor(state: GlobalState) -> str:
    """LangGraph conditional-edge target. Returns the node name to jump to.

    Order:
    1. If the iteration cap was hit OR the run budget is exhausted → reporter.
    2. If a Lead is still un-completed → go there.
    3. Otherwise → reporter (final synthesis for the manager).
    """
    if state.get("iteration", 0) > MAX_ITERATIONS:
        return "reporter"
    if budget_exceeded() is not None:
        return "reporter"

    lead = _next_lead(state)
    if lead is None:
        return "reporter"
    return lead


def mark_completed(state: GlobalState, lead: LeadName) -> dict[str, Any]:
    """Helper Lead nodes call to record completion on the shared state."""
    done = list(state.get("completed") or [])
    if lead not in done:
        done.append(lead)
    return {"completed": done}
