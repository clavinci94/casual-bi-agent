"""HTTP API for the AI²L (assisted) multi-agent investigator.

Two endpoints:

- POST /investigations/assisted
    Starts a multi-agent investigation. Returns 202 + run_id + poll_url
    synchronously; the actual run_graph(...) executes on a bounded thread
    pool so the API stays responsive.

- GET  /investigations/assisted/{run_id}
    Returns the full manager-facing artefact (ReportResult), the strategy
    options, the hierarchical step trace (parent_step_id-linked), and run
    budget usage. Returns the partial state when the run is still in
    flight or finished with errors so clients can render progress.

The design follows the existing single-agent `/investigations/llm` flow:
audit.start_run() creates the run_id up-front so the API can return
immediately, and the worker thread re-attaches via run_id=. The /runs/{id}
dashboard endpoint also keeps working — this router adds a richer view
specifically tailored to the multi-agent output shape.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from biq.agents.multi import graph as multi_graph
from biq.audit import start_run
from biq.db import engine

router = APIRouter(prefix="/investigations/assisted", tags=["investigations"])

_logger = logging.getLogger(__name__)

# Multi-agent runs are I/O-bound (LangGraph + Claude + Postgres + R), so
# threads are the right tool — but each run can burn dollars of LLM cost,
# so we keep concurrency tight. Override with BIQ_ASSISTED_POOL_SIZE.
_MAX_CONCURRENT_RUNS = int(os.environ.get("BIQ_ASSISTED_POOL_SIZE", "2"))
_executor = ThreadPoolExecutor(
    max_workers=_MAX_CONCURRENT_RUNS,
    thread_name_prefix="biq-assisted",
)


# ---------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------


class AssistedInvestigationRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=5,
        max_length=4000,
        description="Free-form business question in any language (Manager-facing reply is in DE).",
    )
    horizon_start: str | None = Field(
        default=None,
        description="ISO date of the investigation window start (post-period). Optional.",
    )
    horizon_end: str | None = Field(
        default=None,
        description="ISO date of the investigation window end (post-period). Optional.",
    )
    target_device: str | None = Field(
        default=None,
        description="Restrict the investigation to one device. Defaults to 'mobile'.",
    )
    target_kpi: str | None = Field(
        default=None, description="KPI focus override (defaults to conversion_rate)."
    )


class AssistedRunHandle(BaseModel):
    run_id: str
    status: str = Field(..., description="'started' on POST.")
    poll_url: str
    detail_url: str


class StepNode(BaseModel):
    step_id: str
    parent_step_id: str | None
    seq: int
    agent_name: str
    agent_level: str | None
    action: str
    latency_ms: int | None
    model: str | None
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None
    input: dict[str, Any] | None
    output: dict[str, Any] | None


class BudgetUsage(BaseModel):
    tokens_used: int
    cost_usd_used: float
    open_questions: list[str] = Field(default_factory=list)


class AssistedRunStatus(BaseModel):
    run_id: str
    status: str  # running | ok | error | aborted (mirrors audit.agent_runs.status)
    question: str | None
    started_at: str | None
    finished_at: str | None
    error_message: str | None
    report: dict[str, Any] | None = None
    strategy_options: list[dict[str, Any]] = Field(default_factory=list)
    risk_level: str | None = None
    open_questions: list[str] = Field(default_factory=list)
    budget: BudgetUsage | None = None
    steps: list[StepNode] = Field(default_factory=list)


# ---------------------------------------------------------------------
# POST — start a run
# ---------------------------------------------------------------------


@router.post("", response_model=AssistedRunHandle, status_code=202)
def start_assisted_investigation(
    payload: AssistedInvestigationRequest,
) -> AssistedRunHandle:
    """Start a multi-agent investigation. Returns immediately with run_id."""
    horizon = _validate_horizon(payload.horizon_start, payload.horizon_end)

    run_id = start_run(trigger="api_assisted", prompt=payload.question)

    def _run() -> None:
        try:
            multi_graph.run_graph(
                question=payload.question,
                horizon=horizon,
                target_kpi=payload.target_kpi,
                target_device=payload.target_device,
                audit=True,
                run_id=run_id,
                trigger="api_assisted",
            )
        except Exception:
            # run_context inside run_graph marks the row as error; we log too.
            _logger.exception("assisted investigation failed (run_id=%s)", run_id)

    _executor.submit(_run)

    return AssistedRunHandle(
        run_id=run_id,
        status="started",
        poll_url=f"/api/investigations/assisted/{run_id}",
        detail_url=f"/api/runs/{run_id}",
    )


def _validate_horizon(start: str | None, end: str | None) -> tuple[str, str] | None:
    if start is None and end is None:
        return None
    if start is None or end is None:
        raise HTTPException(
            status_code=422,
            detail="horizon_start and horizon_end must be set together.",
        )
    if start > end:
        raise HTTPException(status_code=422, detail="horizon_start must be <= horizon_end.")
    return (start, end)


# ---------------------------------------------------------------------
# GET — poll status + read result
# ---------------------------------------------------------------------


@router.get("/{run_id}", response_model=AssistedRunStatus)
def get_assisted_run(run_id: str) -> AssistedRunStatus:
    with engine.connect() as conn:
        run = conn.execute(
            text(
                "SELECT run_id, prompt, status, started_at, finished_at, "
                "       error_message "
                "FROM audit.agent_runs WHERE run_id = :id"
            ),
            {"id": run_id},
        ).first()
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        run_m = run._mapping

        steps_rows = conn.execute(
            text(
                "SELECT step_id, parent_step_id, seq, agent_name, agent_level, "
                "       action, latency_ms, model, tokens_in, tokens_out, "
                "       cost_usd, input, output "
                "FROM audit.agent_steps WHERE run_id = :id ORDER BY seq"
            ),
            {"id": run_id},
        ).all()

    steps = [StepNode(**dict(r._mapping)) for r in steps_rows]
    reporter = next(
        (s for s in steps if s.agent_name == "reporter" and s.output is not None),
        None,
    )
    report = reporter.output.get("report") if reporter else None
    strategy_options = reporter.output.get("strategy_options", []) if reporter else []
    risk_level = reporter.output.get("strategy_risk_level") if reporter else None
    open_questions = reporter.output.get("open_questions", []) if reporter else []

    tokens = sum((s.tokens_in or 0) + (s.tokens_out or 0) for s in steps)
    cost = round(sum(float(s.cost_usd or 0) for s in steps), 6)

    return AssistedRunStatus(
        run_id=run_m["run_id"],
        status=run_m["status"],
        question=run_m["prompt"],
        started_at=run_m["started_at"].isoformat() if run_m["started_at"] else None,
        finished_at=run_m["finished_at"].isoformat() if run_m["finished_at"] else None,
        error_message=run_m["error_message"],
        report=report,
        strategy_options=strategy_options,
        risk_level=risk_level,
        open_questions=open_questions,
        budget=BudgetUsage(tokens_used=tokens, cost_usd_used=cost, open_questions=open_questions),
        steps=steps,
    )
