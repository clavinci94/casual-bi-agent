"""Helpers to write audit.* tables.

Pattern:

    with run_context(trigger="cli", prompt="...") as ctx:
        step_id = log_step(ctx, "anomaly_detector", "scan", input={...})
        log_tool_call(step_id, "sql.kpi.conversion_rate_daily", params={...}, rows=42)
        finish_step(step_id, output={...})
        log_recommendation(ctx.run_id, ...)
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from sqlalchemy import text

from biq.db import engine


@dataclass
class RunContext:
    run_id: str
    trigger: str
    seq: int = 0


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


@contextmanager
def run_context(
    trigger: str,
    prompt: str | None = None,
    user_id: str | None = None,
) -> Iterator[RunContext]:
    """Open an audit.agent_runs row, yield context, mark ok/error on exit."""
    run_id = str(uuid.uuid4())
    ctx = RunContext(run_id=run_id, trigger=trigger)

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit.agent_runs (run_id, user_id, trigger, prompt, status) "
                "VALUES (:run_id, :user_id, :trigger, :prompt, 'running')"
            ),
            {"run_id": run_id, "user_id": user_id, "trigger": trigger, "prompt": prompt},
        )

    try:
        yield ctx
    except Exception as e:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE audit.agent_runs "
                    "SET status='error', error_message=:err, finished_at=now() "
                    "WHERE run_id=:run_id"
                ),
                {"err": str(e)[:1000], "run_id": run_id},
            )
        raise
    else:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE audit.agent_runs SET status='ok', finished_at=now() "
                    "WHERE run_id=:run_id"
                ),
                {"run_id": run_id},
            )


def log_step(
    ctx: RunContext,
    agent_name: str,
    action: str,
    input: dict[str, Any] | None = None,
) -> str:
    """Insert audit.agent_steps row, return step_id."""
    ctx.seq += 1
    step_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit.agent_steps "
                "(step_id, run_id, seq, agent_name, action, input) "
                "VALUES (:step_id, :run_id, :seq, :agent, :action, cast(:input as jsonb))"
            ),
            {
                "step_id": step_id,
                "run_id": ctx.run_id,
                "seq": ctx.seq,
                "agent": agent_name,
                "action": action,
                "input": _json(input),
            },
        )
    return step_id


def finish_step(step_id: str, output: dict[str, Any] | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE audit.agent_steps "
                "SET output = cast(:output as jsonb), "
                "    finished_at = now(), "
                "    latency_ms = (EXTRACT(EPOCH FROM (now() - started_at)) * 1000)::int "
                "WHERE step_id = :step_id"
            ),
            {"step_id": step_id, "output": _json(output)},
        )


def log_tool_call(
    step_id: str,
    tool_name: str,
    params: dict[str, Any],
    result_summary: dict[str, Any] | None = None,
    rows: int = 0,
    cached: bool = False,
    error: str | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit.tool_calls "
                "(step_id, tool_name, params, result_summary, rows_returned, cached, error) "
                "VALUES (:step_id, :tool, cast(:params as jsonb), cast(:summary as jsonb), "
                "        :rows, :cached, :error)"
            ),
            {
                "step_id": step_id,
                "tool": tool_name,
                "params": _json(params),
                "summary": _json(result_summary),
                "rows": rows,
                "cached": cached,
                "error": error,
            },
        )


def log_recommendation(
    run_id: str,
    title: str,
    body: str,
    confidence: float,
    action_type: str,
    risk_level: str,
) -> str:
    rec_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit.recommendations "
                "(rec_id, run_id, title, body, confidence, action_type, risk_level) "
                "VALUES (:rec, :run, :title, :body, :conf, :atype, :risk)"
            ),
            {
                "rec": rec_id,
                "run": run_id,
                "title": title,
                "body": body,
                "conf": confidence,
                "atype": action_type,
                "risk": risk_level,
            },
        )
    return rec_id
