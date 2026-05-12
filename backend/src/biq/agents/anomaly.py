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

    merged = df_now.merge(df_prior, on="device", suffixes=("_now", "_prior"), how="outer").fillna(0)

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


DEVICE_DE = {
    "mobile": "Mobile Geräten",
    "desktop": "Desktop",
    "tablet": "Tablets",
}

KPI_DE = {
    "conversion_rate": "Conversion Rate",
    "aov": "Bestellwert",
    "gross_margin": "Bruttomarge",
}


def _de_date(d: date) -> str:
    """German short date: '7. Apr. 2018'."""
    months = [
        "Jan.",
        "Feb.",
        "März",
        "Apr.",
        "Mai",
        "Juni",
        "Juli",
        "Aug.",
        "Sep.",
        "Okt.",
        "Nov.",
        "Dez.",
    ]
    return f"{d.day}. {months[d.month - 1]} {d.year}"


def _de_pct(value: float) -> str:
    """4.23 → '4,23 %'."""
    return f"{value * 100:.2f}".replace(".", ",") + " %"


def _de_int(value: int) -> str:
    """German thousands separator using a hard space."""
    return f"{value:,}".replace(",", " ")


def narrate(insight: Insight) -> tuple[str, str]:
    """Manager-readable German title + body for an anomaly insight.

    Anti-jargon rules:
    - No table or column names ('kpi.conversion_rate_daily', 'device=mobile').
    - No technical statistics ('severity: medium', 'rolling window').
    - Three clear sections in the body: Worum geht es / Datenbasis /
      Vorschlag. A manager can read just the title and act.
    """
    kpi_label = KPI_DE.get(insight.kpi, insight.kpi)
    segment_label = (
        DEVICE_DE.get(insight.value, insight.value.capitalize())
        if insight.dimension == "device"
        else f"{insight.dimension}={insight.value}"
    )

    direction = "gefallen" if insight.relative_change < 0 else "gestiegen"
    rel_pct = abs(insight.relative_change) * 100
    rel_str = f"{rel_pct:.1f}".replace(".", ",") + " %"

    severity_de = {
        "high": "dringend",
        "medium": "zu prüfen",
        "low": "Hinweis",
    }.get(insight.severity, insight.severity)

    title = f"{kpi_label} auf {segment_label} um {rel_str} {direction}"

    period_now = f"{_de_date(insight.period_now[0])} bis {_de_date(insight.period_now[1])}"
    period_prior = f"{_de_date(insight.period_prior[0])} bis {_de_date(insight.period_prior[1])}"

    body = (
        f"Worum geht es: Die {kpi_label} auf {segment_label} ist "
        f"im Zeitraum {period_now} von {_de_pct(insight.metric_prior)} auf "
        f"{_de_pct(insight.metric_now)} {direction} — ein Rückgang von "
        f"{rel_str} gegenüber dem Vergleichszeitraum {period_prior}.\n\n"
        f"Datenbasis: {_de_int(insight.sessions_now)} Sitzungen im aktuellen "
        f"Zeitfenster (Vorperiode: {_de_int(insight.sessions_prior)}). "
        f"Einstufung: {severity_de}.\n\n"
        f"Vorschlag: Eine vertiefte Kausalanalyse starten, um zu prüfen, ob "
        f"ein konkretes Software-Release oder eine Marketing-Kampagne in "
        f"diesem Zeitraum den Effekt erklärt. Sobald eine Ursache "
        f"bestätigt ist, legen wir Ihnen eine konkrete Massnahme zur "
        f"Freigabe vor."
    )
    return title, body


def _pending_duplicate_exists(
    component: str,
    period_start: str,
    period_end: str,
    kpi: str,
) -> bool:
    """Return True if a pending recommendation for the same anomaly
    already exists. Prevents flooding the queue when the detector is
    triggered repeatedly (cron, manual scan, eval suite).

    The "same anomaly" key is (kpi, component, period_start, period_end).
    The KG insight carries those properties; we join on the audit row's
    run_id to find them quickly.
    """
    sql = text(
        "SELECT 1 "
        "FROM audit.recommendations r "
        "JOIN kg.nodes n "
        "  ON n.external_ref = 'rec:' || r.rec_id "
        " AND n.label = 'Insight' "
        "WHERE r.status = 'pending' "
        "  AND n.properties->>'component'    = :component "
        "  AND n.properties->>'kpi'          = :kpi "
        "  AND n.properties->>'period_start' = :ps "
        "  AND n.properties->>'period_end'   = :pe "
        "LIMIT 1"
    )
    with engine.connect() as conn:
        row = conn.execute(
            sql,
            {
                "component": component,
                "kpi": kpi,
                "ps": period_start,
                "pe": period_end,
            },
        ).first()
    return row is not None


def run(reference_day: date | None = None) -> dict[str, Any]:
    """Single end-to-end scan. Returns insights + recommendation ids.

    Skips creating a duplicate recommendation when the same anomaly
    (kpi + component + period) is already pending. This makes the
    detector safe to run repeatedly (cron, manual, evals) without
    flooding the HITL queue.
    """
    with run_context(
        trigger="cli",
        prompt="Routine-Überwachung der Conversion Rate nach Endgerät",
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
        skipped = 0
        for ins in insights:
            component = f"{ins.dimension}={ins.value}"
            period_start, period_end = str(ins.period_now[0]), str(ins.period_now[1])

            if _pending_duplicate_exists(
                component=component,
                period_start=period_start,
                period_end=period_end,
                kpi=ins.kpi,
            ):
                skipped += 1
                continue

            title, body = narrate(ins)
            rec_ids.append(
                log_recommendation(
                    run_id=ctx.run_id,
                    title=title,
                    body=body,
                    confidence=0.6 if ins.severity == "high" else 0.4,
                    action_type="read_only",
                    risk_level=ins.severity,
                    component=component,
                    period=(period_start, period_end),
                    kg_extra={"kpi": ins.kpi, "relative_change": ins.relative_change},
                )
            )

        return {
            "run_id": ctx.run_id,
            "reference_day": str(ref),
            "insights": [i.to_dict() for i in insights],
            "recommendation_ids": rec_ids,
            "skipped_duplicates": skipped,
        }
