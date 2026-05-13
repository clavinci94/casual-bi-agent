"""Agent-run audit trail."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from biq.db import engine

router = APIRouter(prefix="/runs", tags=["runs"])


class TopRecommendation(BaseModel):
    """Compact summary of the highest-impact recommendation produced by
    this run — surfaced on the dashboard activity strip so a manager can
    see the outcome without drilling into the run detail."""

    rec_id: str
    title: str
    risk_level: str
    status: str


class AgentRun(BaseModel):
    run_id: str
    user_id: str | None
    trigger: str
    prompt: str | None
    status: str
    started_at: datetime
    finished_at: datetime | None
    cost_usd: float | None
    top_recommendation: TopRecommendation | None = None


class AgentStep(BaseModel):
    step_id: str
    seq: int
    agent_name: str
    action: str
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    latency_ms: int | None


class ToolCall(BaseModel):
    call_id: str
    tool_name: str
    params: dict[str, Any]
    rows_returned: int
    error: str | None


class RunDetail(BaseModel):
    run: AgentRun
    steps: list[AgentStep]
    tool_calls: list[ToolCall]


@router.get("", response_model=list[AgentRun])
def list_runs(
    limit: Annotated[int, Query(le=200)] = 50,
    exclude_triggers: Annotated[
        list[str] | None,
        Query(
            description=(
                "Trigger values to filter out, e.g. exclude_triggers=test. "
                "Useful for keeping pytest fixtures off the dashboard."
            ),
        ),
    ] = None,
) -> list[AgentRun]:
    params: dict[str, object] = {"limit": limit}
    where = ""
    if exclude_triggers:
        where = "WHERE trigger <> ALL(:excluded)"
        params["excluded"] = list(exclude_triggers)
    # LATERAL subquery picks the single most-relevant recommendation per
    # run: prefer high > medium > low risk, tie-break by created_at.
    sql = text(
        f"SELECT r.run_id, r.user_id, r.trigger, r.prompt, r.status, "
        f"       r.started_at, r.finished_at, r.cost_usd, "
        f"       rec.rec_id, rec.title, rec.risk_level, rec.status AS rec_status "
        f"FROM audit.agent_runs r "
        f"LEFT JOIN LATERAL ("
        f"  SELECT rec_id, title, risk_level, status "
        f"  FROM audit.recommendations "
        f"  WHERE run_id = r.run_id "
        f"  ORDER BY CASE risk_level "
        f"             WHEN 'high' THEN 0 "
        f"             WHEN 'medium' THEN 1 "
        f"             WHEN 'low' THEN 2 "
        f"             ELSE 3 END, "
        f"           created_at DESC "
        f"  LIMIT 1 "
        f") rec ON true "
        f"{where.replace('WHERE trigger', 'WHERE r.trigger')} "
        f"ORDER BY r.started_at DESC LIMIT :limit"
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, params).all()
    return [_row_to_run(r) for r in rows]


def _row_to_run(r: Any) -> AgentRun:
    m = r._mapping
    top = None
    if m["rec_id"] is not None:
        top = TopRecommendation(
            rec_id=m["rec_id"],
            title=m["title"],
            risk_level=m["risk_level"],
            status=m["rec_status"],
        )
    return AgentRun(
        run_id=m["run_id"],
        user_id=m["user_id"],
        trigger=m["trigger"],
        prompt=m["prompt"],
        status=m["status"],
        started_at=m["started_at"],
        finished_at=m["finished_at"],
        cost_usd=m["cost_usd"],
        top_recommendation=top,
    )


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str) -> RunDetail:
    with engine.connect() as conn:
        run_row = conn.execute(
            text(
                "SELECT r.run_id, r.user_id, r.trigger, r.prompt, r.status, "
                "       r.started_at, r.finished_at, r.cost_usd, "
                "       rec.rec_id, rec.title, rec.risk_level, "
                "       rec.status AS rec_status "
                "FROM audit.agent_runs r "
                "LEFT JOIN LATERAL ( "
                "  SELECT rec_id, title, risk_level, status "
                "  FROM audit.recommendations "
                "  WHERE run_id = r.run_id "
                "  ORDER BY CASE risk_level "
                "             WHEN 'high' THEN 0 "
                "             WHEN 'medium' THEN 1 "
                "             WHEN 'low' THEN 2 "
                "             ELSE 3 END, "
                "           created_at DESC "
                "  LIMIT 1 "
                ") rec ON true "
                "WHERE r.run_id = :id"
            ),
            {"id": run_id},
        ).first()
        if not run_row:
            raise HTTPException(status_code=404, detail="run not found")

        step_rows = conn.execute(
            text(
                "SELECT step_id, seq, agent_name, action, input, output, latency_ms "
                "FROM audit.agent_steps WHERE run_id = :id ORDER BY seq"
            ),
            {"id": run_id},
        ).all()

        call_rows = conn.execute(
            text(
                "SELECT tc.call_id, tc.tool_name, tc.params, "
                "       tc.rows_returned, tc.error "
                "FROM audit.tool_calls tc "
                "JOIN audit.agent_steps s ON s.step_id = tc.step_id "
                "WHERE s.run_id = :id ORDER BY s.seq, tc.called_at"
            ),
            {"id": run_id},
        ).all()

    return RunDetail(
        run=_row_to_run(run_row),
        steps=[AgentStep(**dict(s._mapping)) for s in step_rows],
        tool_calls=[ToolCall(**dict(c._mapping)) for c in call_rows],
    )
