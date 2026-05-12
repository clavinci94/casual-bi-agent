"""Agent-run audit trail."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from biq.db import engine

router = APIRouter(prefix="/runs", tags=["runs"])


class AgentRun(BaseModel):
    run_id: str
    user_id: str | None
    trigger: str
    prompt: str | None
    status: str
    started_at: datetime
    finished_at: datetime | None
    cost_usd: float | None


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
    sql = text(
        f"SELECT run_id, user_id, trigger, prompt, status, "
        f"       started_at, finished_at, cost_usd "
        f"FROM audit.agent_runs {where} "
        f"ORDER BY started_at DESC LIMIT :limit"
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, params).all()
    return [AgentRun(**dict(r._mapping)) for r in rows]


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str) -> RunDetail:
    with engine.connect() as conn:
        run_row = conn.execute(
            text(
                "SELECT run_id, user_id, trigger, prompt, status, "
                "       started_at, finished_at, cost_usd "
                "FROM audit.agent_runs WHERE run_id = :id"
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
        run=AgentRun(**dict(run_row._mapping)),
        steps=[AgentStep(**dict(s._mapping)) for s in step_rows],
        tool_calls=[ToolCall(**dict(c._mapping)) for c in call_rows],
    )
