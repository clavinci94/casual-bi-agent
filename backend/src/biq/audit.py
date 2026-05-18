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
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

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


def start_run(
    trigger: str,
    prompt: str | None = None,
    user_id: str | None = None,
) -> str:
    """Insert an audit.agent_runs row in 'running' state and return its id.

    Use this when you need the run_id BEFORE the work begins — typically
    from an API handler that returns immediately and spawns the actual
    agent loop on a background thread, so the client can poll the run.
    Pair with `run_context(..., run_id=<that id>)` inside the worker.
    """
    run_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit.agent_runs (run_id, user_id, trigger, prompt, status) "
                "VALUES (:run_id, :user_id, :trigger, :prompt, 'running')"
            ),
            {"run_id": run_id, "user_id": user_id, "trigger": trigger, "prompt": prompt},
        )
    return run_id


@contextmanager
def run_context(
    trigger: str,
    prompt: str | None = None,
    user_id: str | None = None,
    run_id: str | None = None,
) -> Iterator[RunContext]:
    """Open (or attach to) an audit.agent_runs row.

    When `run_id` is None: INSERT a new row, yield context, UPDATE on exit.
    When `run_id` is provided: the row was already inserted (e.g. via
    `start_run` from an API handler). We do NOT re-insert; we still UPDATE
    on exit so the lifecycle (ok / error + finished_at) is recorded.
    """
    if run_id is None:
        run_id = str(uuid.uuid4())
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO audit.agent_runs (run_id, user_id, trigger, prompt, status) "
                    "VALUES (:run_id, :user_id, :trigger, :prompt, 'running')"
                ),
                {
                    "run_id": run_id,
                    "user_id": user_id,
                    "trigger": trigger,
                    "prompt": prompt,
                },
            )

    ctx = RunContext(run_id=run_id, trigger=trigger)

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
    parent_step_id: str | None = None,
    agent_level: str | None = None,
    model: str | None = None,
) -> str:
    """Insert audit.agent_steps row, return step_id.

    Multi-agent extensions are all nullable to keep single-agent callers
    working unchanged: pass `parent_step_id` to record a sub-worker under
    its lead, and `agent_level` ('supervisor' | 'lead' | 'sub') so the
    UI can group rows by hierarchy level.
    """
    ctx.seq += 1
    step_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit.agent_steps "
                "(step_id, run_id, parent_step_id, seq, agent_name, "
                " agent_level, action, input, model) "
                "VALUES (:step_id, :run_id, :parent, :seq, :agent, "
                "        :level, :action, cast(:input as jsonb), :model)"
            ),
            {
                "step_id": step_id,
                "run_id": ctx.run_id,
                "parent": parent_step_id,
                "seq": ctx.seq,
                "agent": agent_name,
                "level": agent_level,
                "action": action,
                "input": _json(input),
                "model": model,
            },
        )
    return step_id


def finish_step(
    step_id: str,
    output: dict[str, Any] | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd: float | None = None,
) -> None:
    """Mark the step finished and (optionally) attach LLM cost telemetry."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE audit.agent_steps "
                "SET output = cast(:output as jsonb), "
                "    finished_at = now(), "
                "    latency_ms = (EXTRACT(EPOCH FROM (now() - started_at)) * 1000)::int, "
                "    tokens_in = COALESCE(:tin, tokens_in), "
                "    tokens_out = COALESCE(:tout, tokens_out), "
                "    cost_usd = COALESCE(:cost, cost_usd) "
                "WHERE step_id = :step_id"
            ),
            {
                "step_id": step_id,
                "output": _json(output),
                "tin": tokens_in,
                "tout": tokens_out,
                "cost": cost_usd,
            },
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
    *,
    component: str | None = None,
    period: tuple[str, str] | None = None,
    period_prior: tuple[str, str] | None = None,
    kg_extra: dict[str, Any] | None = None,
) -> str:
    """Persist a recommendation AND mirror it as a kg.Insight node.

    The Insight is what the learning-loop queries — its external_ref is
    `rec:<rec_id>` and it carries component/severity/period in properties.
    """
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

    # KG mirror — imported here to avoid a top-level circular dep, since
    # tools/kg.py imports from biq.db which doesn't touch audit.
    try:
        from biq.tools import kg as kg_tools

        kg_tools.record_insight_for_recommendation(
            rec_id=rec_id,
            title=title,
            component=component,
            severity=risk_level,
            period=period,
            period_prior=period_prior,
            run_id=run_id,
            extra=kg_extra,
        )
    except Exception:
        # KG failures must never block the audit write
        pass

    # Slack alert — only high-risk so we don't spam the channel. Failures
    # in the integration must never propagate to the audit write.
    if risk_level == "high":
        try:
            from biq.integrations import slack

            slack.notify_recommendation(
                rec_id=rec_id,
                title=title,
                body=body,
                risk_level=risk_level,
                confidence=confidence,
            )
        except Exception:
            pass

    return rec_id
