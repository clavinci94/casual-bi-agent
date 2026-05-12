"""Knowledge-graph queries — what we've learned from past decisions."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from biq.tools import kg as kg_tools

router = APIRouter(prefix="/kg", tags=["knowledge-graph"])


@router.get("/insights")
def list_insights(
    limit: Annotated[int, Query(le=200)] = 50,
    exclude_triggers: Annotated[
        list[str] | None,
        Query(
            description=(
                "Drop Insights produced by runs with these triggers (e.g. 'test'). "
                "Insights without a run_id are kept regardless."
            ),
        ),
    ] = None,
) -> list[dict[str, Any]]:
    """Recent Insight nodes — every recommendation that landed."""
    return kg_tools.list_recent_insights(limit=limit, exclude_triggers=exclude_triggers)


@router.get("/learnings/{component}")
def learnings_for_component(
    component: str,
    days_back: Annotated[int, Query(ge=1, le=730)] = 180,
) -> dict[str, Any]:
    """What past insights, decisions, and outcomes exist for this component.

    Component is a free-form string like 'mobile_checkout', 'device=mobile',
    or 'paid_search'. The lookup matches against Insight properties and
    transitively against linked Hypotheses.
    """
    return kg_tools.lookup_past_decisions(component=component, days_back=days_back)


class OutcomeRequest(BaseModel):
    decision_id: str = Field(..., description="kg.Decision node_id")
    metric: str = Field(..., description="e.g. 'conversion_rate'")
    expected_effect: float | None = None
    observed_effect: float | None = None
    period_start: str
    period_end: str
    notes: str | None = None


class OutcomeResponse(BaseModel):
    outcome_id: str | None
    decision_id: str
    status: str


@router.post("/outcomes", response_model=OutcomeResponse)
def record_outcome(payload: OutcomeRequest) -> OutcomeResponse:
    """Attach a measured Outcome to a Decision — closes the learning loop.

    Typically called by an n8n cron job after the observation window.
    """
    outcome_id = kg_tools.record_outcome(
        decision_id=payload.decision_id,
        metric=payload.metric,
        expected=payload.expected_effect,
        observed=payload.observed_effect,
        period=(payload.period_start, payload.period_end),
        notes=payload.notes,
    )
    if outcome_id is None:
        raise HTTPException(status_code=404, detail="decision not found")
    return OutcomeResponse(
        outcome_id=outcome_id, decision_id=payload.decision_id, status="recorded"
    )
