"""Trigger investigations from HTTP.

Three endpoints:
- POST /investigations/anomaly: heuristic detector (no LLM, fast, synchronous)
- POST /investigations/graph:   LangGraph multi-agent (calls R service, sync)
- POST /investigations/llm:     LLM-driven investigator. Returns 202 + run_id
                                immediately; the actual loop runs on a
                                background thread and writes to audit.*.
                                Clients poll GET /api/runs/{run_id}.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from biq.agents import anomaly as anomaly_agent
from biq.agents import graph as graph_agent
from biq.agents import investigator as llm_investigator
from biq.audit import start_run
from biq.config import settings

router = APIRouter(prefix="/investigations", tags=["investigations"])

_logger = logging.getLogger(__name__)

# Bounded pool so a runaway demand doesn't open dozens of expensive LLM calls
# in parallel. Overflow requests block in the queue (or fail fast — see below).
_MAX_CONCURRENT_LLM_RUNS = int(os.environ.get("BIQ_LLM_POOL_SIZE", "2"))
_llm_executor = ThreadPoolExecutor(
    max_workers=_MAX_CONCURRENT_LLM_RUNS,
    thread_name_prefix="biq-llm",
)


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


class LlmInvestigationRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=5,
        max_length=4000,
        description="Free-form business question for the LLM investigator.",
    )
    model: str | None = Field(
        default=None,
        description="Override the default Claude model (e.g. cheaper Haiku).",
    )
    max_iterations: int = Field(default=10, ge=1, le=20)
    max_input_tokens: int = Field(default=200_000, ge=1_000)
    max_output_tokens: int = Field(default=20_000, ge=500)


class LlmInvestigationResponse(BaseModel):
    run_id: str
    status: str  # "started"
    poll_url: str


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


@router.post("/llm", response_model=LlmInvestigationResponse, status_code=202)
def start_llm_investigation(
    payload: LlmInvestigationRequest,
) -> LlmInvestigationResponse:
    """Start an LLM-driven investigation. Returns immediately with the run_id.

    The actual agent loop runs on a thread pool — the client polls
    `GET /api/runs/{run_id}` to follow progress and read the final answer.
    """
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY not configured on the backend.",
        )

    run_id = start_run(trigger="api", prompt=payload.question)

    def _run() -> None:
        try:
            llm_investigator.investigate(
                payload.question,
                model=payload.model or llm_investigator.DEFAULT_MODEL,
                max_iterations=payload.max_iterations,
                max_input_tokens=payload.max_input_tokens,
                max_output_tokens=payload.max_output_tokens,
                trigger="api",
                run_id=run_id,
            )
        except Exception:
            # The run_context inside investigate() already marks the row
            # as error. Surface the traceback to the server log either way.
            _logger.exception("LLM investigation failed (run_id=%s)", run_id)

    _llm_executor.submit(_run)

    return LlmInvestigationResponse(
        run_id=run_id,
        status="started",
        poll_url=f"/api/runs/{run_id}",
    )
