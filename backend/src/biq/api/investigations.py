"""Trigger investigations from HTTP.

Two endpoints:
- POST /investigations/anomaly: heuristic detector (no LLM, fast)
- POST /investigations/graph: LangGraph multi-agent (calls R service)

Both run synchronously. For a production system add async job + polling
via the audit.agent_runs table.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from biq.agents import anomaly as anomaly_agent
from biq.agents import graph as graph_agent

router = APIRouter(prefix="/investigations", tags=["investigations"])


class AnomalyScanRequest(BaseModel):
    reference_date: date | None = Field(
        default=None,
        description="Reference day. Defaults to the latest day with data.",
    )


class GraphInvestigationRequest(BaseModel):
    target_device: str = "mobile"
    pre_start: str = "2018-02-15"
    pre_end: str = "2018-04-14"
    post_start: str = "2018-04-15"
    post_end: str = "2018-05-10"
    question: str | None = None


@router.post("/anomaly")
def scan_anomaly(payload: AnomalyScanRequest) -> dict[str, Any]:
    return anomaly_agent.run(reference_day=payload.reference_date)


@router.post("/graph")
def run_graph(payload: GraphInvestigationRequest) -> dict[str, Any]:
    return graph_agent.run_graph(
        target_device=payload.target_device,
        pre_period=(payload.pre_start, payload.pre_end),
        post_period=(payload.post_start, payload.post_end),
        question=payload.question,
    )
