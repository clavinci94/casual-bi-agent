"""Heuristic anomaly detector for KPI deviations.

V1 is rule-based: rolling-window comparison on conversion_rate by device.
The structure (detect -> narrate -> recommend) mirrors how the LLM-driven
agent will work in v2 once the MCP server layer is in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import text

from biq.audit import (
    RunContext,
    finish_step,
    log_recommendation,
    log_step,
    log_tool_call,
    run_context,
)
from biq.db import engine

# Defaults tuned to surface the mobile_checkout_v2 ground truth.
WINDOW_DAYS = 28
DROP_THRESHOLD = 0.15  # relative change vs prior window
MIN_SESSIONS = 100


@dataclass
class Insight:
    kpi: str
    dimension: str
    value: str
    period_now: tuple[date, date]
    period_prior: tuple[date, date]
    metric_now: float
    metric_prior: float
    relative_change: float
    sessions_now: int
    sessions_prior: int
    severity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kpi": self.kpi,
            "dimension": self.dimension,
            "value": self.value,
            "period_now": [str(self.period_now[0]), str(self.period_now[1])],
            "period_prior": [str(self.period_prior[0]), str(self.period_prior[1])],
            "metric_now_pct": round(self.metric_now * 100, 4),
            "metric_prior_pct": round(self.metric_prior * 100, 4),
            "relative_change_pct": round(self.relative_change * 100, 2),
            "sessions_now": self.sessions_now,
            "sessions_prior": self.sessions_prior,
            "severity": self.severity,
        }


def _severity(rel: float, sessions: int) -> str:
    abs_rel = abs(rel)
    if abs_rel >= 0.30 and sessions >= 300:
        return "high"
    if abs_rel >= 0.15 and sessions >= MIN_SESSIONS:
        return "medium"
    return "low"


def _latest_kpi_day() -> date | None:
    with engine.connect() as conn:
        result = conn.execute(text("SELECT MAX(day) FROM kpi.conversion_rate_daily"))
        return result.scalar_one_or_none()


def detect_by_device(
    reference_day: date,
    step_id: str,
    window_days: int = WINDOW_DAYS,
    threshold: float = DROP_THRESHOLD,
) -> list[Insight]:
    now_end = reference_day
    now_start = now_end - timedelta(days=window_days)
    prior_end = now_start
    prior_start = prior_end - timedelta(days=window_days)

    sql = text(
        "SELECT device, "
        "       SUM(sessions)::int    AS sessions, "
        "       SUM(conversions)::int AS conversions "
        "FROM kpi.conversion_rate_daily "
        "WHERE day >= :start AND day < :end "
        "GROUP BY device"
    )

    with engine.connect() as conn:
        df_now = pd.read_sql(sql, conn, params={"start": now_start, "end": now_end})
        df_prior = pd.read_sql(sql, conn, params={"start": prior_start, "end": prior_end})

    log_tool_call(
        step_id,
        "sql.kpi.conversion_rate_daily",
        params={
            "window_days": window_days,
            "by": "device",
            "now": [str(now_start), str(now_end)],
            "prior": [str(prior_start), str(prior_end)],
        },
        result_summary={"rows_now": len(df_now), "rows_prior": len(df_prior)},
        rows=len(df_now) + len(df_prior),
    )

    merged = df_now.merge(
        df_prior, on="device", suffixes=("_now", "_prior"), how="outer"
    ).fillna(0)

    insights: list[Insight] = []
    for _, r in merged.iterrows():
        s_now, s_prior = int(r["sessions_now"]), int(r["sessions_prior"])
        c_now, c_prior = int(r["conversions_now"]), int(r["conversions_prior"])
        if s_now < MIN_SESSIONS or s_prior < MIN_SESSIONS:
            continue
        cr_now = c_now / s_now
        cr_prior = c_prior / s_prior
        if cr_prior == 0:
            continue
        rel = (cr_now - cr_prior) / cr_prior
        if abs(rel) < threshold:
            continue
        insights.append(
            Insight(
                kpi="conversion_rate",
                dimension="device",
                value=str(r["device"]),
                period_now=(now_start, now_end),
                period_prior=(prior_start, prior_end),
                metric_now=cr_now,
                metric_prior=cr_prior,
                relative_change=rel,
                sessions_now=s_now,
                sessions_prior=s_prior,
                severity=_severity(rel, min(s_now, s_prior)),
            )
        )

    return insights


def narrate(insight: Insight) -> tuple[str, str]:
    direction = "fell" if insight.relative_change < 0 else "rose"
    rel_pct = abs(insight.relative_change) * 100
    title = (
        f"conversion_rate on {insight.value} {direction} "
        f"{rel_pct:.1f}% ({insight.severity})"
    )
    body = (
        f"Conversion rate for {insight.dimension}={insight.value} {direction} "
        f"from {insight.metric_prior * 100:.2f}% to {insight.metric_now * 100:.2f}% "
        f"comparing window {insight.period_now[0]}..{insight.period_now[1]} "
        f"vs prior {insight.period_prior[0]}..{insight.period_prior[1]}.\n\n"
        f"Volume: {insight.sessions_now:,} sessions now vs "
        f"{insight.sessions_prior:,} prior.\n"
        f"Severity: {insight.severity}.\n\n"
        f"Next steps: cross-reference with raw.releases and raw.campaigns active "
        f"in the period; route to causal agent for an effect estimate."
    )
    return title, body


def run(reference_day: date | None = None) -> dict[str, Any]:
    """Single end-to-end scan. Returns insights + recommendation ids."""
    with run_context(
        trigger="cli",
        prompt="Scan conversion_rate for anomalies by device",
    ) as ctx:
        step_id = log_step(
            ctx,
            agent_name="anomaly_detector",
            action="scan_by_device",
            input={"reference_day": str(reference_day)},
        )

        ref = reference_day or _latest_kpi_day()
        if ref is None:
            finish_step(step_id, {"error": "no data in kpi.conversion_rate_daily"})
            return {"run_id": ctx.run_id, "reference_day": None, "insights": []}

        insights = detect_by_device(ref, step_id=step_id)
        finish_step(step_id, {"n_insights": len(insights), "reference_day": str(ref)})

        rec_ids: list[str] = []
        for ins in insights:
            title, body = narrate(ins)
            rec_ids.append(
                log_recommendation(
                    run_id=ctx.run_id,
                    title=title,
                    body=body,
                    confidence=0.6 if ins.severity == "high" else 0.4,
                    action_type="read_only",
                    risk_level=ins.severity,
                )
            )

        return {
            "run_id": ctx.run_id,
            "reference_day": str(ref),
            "insights": [i.to_dict() for i in insights],
            "recommendation_ids": rec_ids,
        }
