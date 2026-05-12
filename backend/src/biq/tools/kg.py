"""Knowledge-graph layer: organisational memory.

Every recommendation that lands in audit.recommendations creates a
kg.Insight node. Every HITL decision creates a kg.Decision node and a
LED_TO edge. The graph agent's causal_node also creates Hypothesis +
Evidence nodes with the estimated effect on the BACKS edge.

This means the system accumulates:
    Insight  -[LED_TO]->     Decision  -[RESULTED_IN]->  Outcome
        \\
         `-[SUPPORTS]->   Hypothesis  -[BACKS]->        Evidence

…which is what agents query via `lookup_past_decisions(component)` to
answer "have we seen this pattern before?".

Schema lives in db/schemas/04_kg.sql (kg.nodes + kg.edges + kg.aging
view) — id columns are text (psycopg3 compat), properties are jsonb.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from biq.db import engine


def _new_id() -> str:
    return str(uuid.uuid4())


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str)


# ---- Nodes -------------------------------------------------------------


def create_node(
    label: str,
    external_ref: str | None = None,
    properties: dict[str, Any] | None = None,
) -> str:
    """Insert a node; return its node_id.

    UNIQUE (label, external_ref) means we no-op on duplicate refs — handy
    for entities like Customer or Product that may surface in many runs.
    """
    node_id = _new_id()
    with engine.begin() as conn:
        if external_ref:
            existing = conn.execute(
                text("SELECT node_id FROM kg.nodes WHERE label = :label AND external_ref = :ref"),
                {"label": label, "ref": external_ref},
            ).first()
            if existing:
                return str(existing[0])

        conn.execute(
            text(
                "INSERT INTO kg.nodes (node_id, label, external_ref, properties) "
                "VALUES (:id, :label, :ref, cast(:props as jsonb))"
            ),
            {
                "id": node_id,
                "label": label,
                "ref": external_ref,
                "props": _json(properties or {}),
            },
        )
    return node_id


def create_edge(
    from_node: str,
    to_node: str,
    label: str,
    properties: dict[str, Any] | None = None,
    *,
    effect_size: float | None = None,
    ci_lower: float | None = None,
    ci_upper: float | None = None,
    method: str | None = None,
    confidence: float | None = None,
) -> str:
    """Insert an edge; return its edge_id."""
    edge_id = _new_id()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO kg.edges "
                "(edge_id, from_node, to_node, label, properties, "
                " effect_size, ci_lower, ci_upper, method, confidence) "
                "VALUES (:id, :f, :t, :label, cast(:props as jsonb), "
                " :eff, :lo, :hi, :method, :conf)"
            ),
            {
                "id": edge_id,
                "f": from_node,
                "t": to_node,
                "label": label,
                "props": _json(properties or {}),
                "eff": effect_size,
                "lo": ci_lower,
                "hi": ci_upper,
                "method": method,
                "conf": confidence,
            },
        )
    return edge_id


# ---- Lookups -----------------------------------------------------------


def lookup_past_decisions(component: str, days_back: int = 180) -> dict[str, Any]:
    """Return prior insights + decisions + outcomes for a given component.

    Component is matched against Insight.properties->>'component' or against
    the linked Hypothesis.properties->>'component'.
    """
    sql = text(
        """
        WITH insight_nodes AS (
            SELECT n.node_id, n.properties, n.created_at
            FROM kg.nodes n
            WHERE n.label = 'Insight'
              AND n.created_at >= now() - make_interval(days => :days_back)
              AND (
                  n.properties->>'component' = :component
                  OR EXISTS (
                      SELECT 1 FROM kg.edges e
                      JOIN kg.nodes h ON h.node_id = e.to_node
                      WHERE e.from_node = n.node_id
                        AND h.label = 'Hypothesis'
                        AND h.properties->>'component' = :component
                  )
              )
        ),
        decisions AS (
            SELECT i.node_id AS insight_id,
                   d.node_id  AS decision_id,
                   d.properties AS decision_props,
                   d.created_at AS decided_at
            FROM insight_nodes i
            JOIN kg.edges e ON e.from_node = i.node_id AND e.label = 'LED_TO'
            JOIN kg.nodes d ON d.node_id = e.to_node AND d.label = 'Decision'
        ),
        outcomes AS (
            SELECT dec.decision_id,
                   o.properties AS outcome_props,
                   o.created_at AS measured_at
            FROM decisions dec
            JOIN kg.edges e ON e.from_node = dec.decision_id AND e.label = 'RESULTED_IN'
            JOIN kg.nodes o ON o.node_id = e.to_node AND o.label = 'Outcome'
        )
        SELECT
            i.node_id    AS insight_id,
            i.properties AS insight_props,
            i.created_at AS insight_at,
            d.decision_id, d.decision_props, d.decided_at,
            o.outcome_props, o.measured_at
        FROM insight_nodes i
        LEFT JOIN decisions d ON d.insight_id = i.node_id
        LEFT JOIN outcomes  o ON o.decision_id = d.decision_id
        ORDER BY i.created_at DESC
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"component": component, "days_back": days_back}).all()

    insights: list[dict[str, Any]] = []
    for r in rows:
        m = r._mapping
        insights.append(
            {
                "insight_id": m["insight_id"],
                "insight_at": m["insight_at"],
                "insight": m["insight_props"],
                "decision_id": m["decision_id"],
                "decision_at": m["decided_at"],
                "decision": m["decision_props"],
                "outcome_at": m["measured_at"],
                "outcome": m["outcome_props"],
            }
        )

    return {
        "component": component,
        "days_back": days_back,
        "n_insights": len(insights),
        "n_decided": sum(1 for r in insights if r["decision_id"]),
        "n_measured": sum(1 for r in insights if r["outcome_at"]),
        "insights": insights,
    }


_INSIGHT_STATUS_SQL = """
SELECT n.node_id, n.external_ref, n.properties, n.created_at,
       d.node_id      AS decision_id,
       d.properties   AS decision_props,
       o.node_id      AS outcome_id,
       o.properties   AS outcome_props
FROM kg.nodes n
LEFT JOIN audit.agent_runs ar
  ON ar.run_id = (n.properties->>'run_id')
LEFT JOIN kg.edges led
  ON led.from_node = n.node_id AND led.label = 'LED_TO'
LEFT JOIN kg.nodes d
  ON d.node_id = led.to_node AND d.label = 'Decision'
LEFT JOIN kg.edges res
  ON res.from_node = d.node_id AND res.label = 'RESULTED_IN'
LEFT JOIN kg.nodes o
  ON o.node_id = res.to_node AND o.label = 'Outcome'
WHERE n.label = 'Insight'
{where_extra}
ORDER BY n.created_at DESC
LIMIT :limit
"""


def list_recent_insights(
    limit: int = 50,
    exclude_triggers: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Recent Insight nodes, optionally filtered by parent run's trigger.

    Insight nodes carry `properties->>'run_id'` linking back to
    audit.agent_runs. When `exclude_triggers` is given we LEFT JOIN and
    drop matches — that hides pytest fixtures from the dashboard while
    still surfacing legacy Insights without a run_id (the JOIN preserves
    them via the IS NULL clause).
    """
    params: dict[str, Any] = {"limit": limit}
    where_extra = ""
    if exclude_triggers:
        where_extra = "AND (ar.trigger IS NULL OR ar.trigger <> ALL(:excluded))"
        params["excluded"] = list(exclude_triggers)

    sql = text(_INSIGHT_STATUS_SQL.format(where_extra=where_extra))
    with engine.connect() as conn:
        rows = conn.execute(sql, params).all()
    return [
        {
            "insight_id": r[0],
            "external_ref": r[1],
            "properties": r[2],
            "created_at": r[3],
            "decision": _coalesce_decision(r[4], r[5]),
            "outcome": _coalesce_outcome(r[6], r[7]),
        }
        for r in rows
    ]


def _coalesce_decision(
    node_id: str | None, props: dict[str, Any] | None
) -> dict[str, Any] | None:
    if not node_id:
        return None
    p = props or {}
    return {
        "decision_id": node_id,
        "decision": p.get("decision"),
        "approver": p.get("approver"),
        "decided_at": p.get("decided_at"),
        "outcome_due_at": p.get("outcome_due_at"),
    }


def _coalesce_outcome(
    node_id: str | None, props: dict[str, Any] | None
) -> dict[str, Any] | None:
    if not node_id:
        return None
    p = props or {}
    return {
        "outcome_id": node_id,
        "metric": p.get("metric"),
        "expected_effect": p.get("expected_effect"),
        "observed_effect": p.get("observed_effect"),
        "period_start": p.get("period_start"),
        "period_end": p.get("period_end"),
        "measured_at": p.get("measured_at"),
        "notes": p.get("notes"),
    }


# ---- Domain-specific helpers used by the wiring ------------------------


def record_insight_for_recommendation(
    rec_id: str,
    title: str,
    component: str | None = None,
    severity: str | None = None,
    period: tuple[str, str] | None = None,
    period_prior: tuple[str, str] | None = None,
    run_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Create an Insight node for a freshly-logged recommendation.

    `period_prior` is the pre-anomaly baseline window — stored so the
    outcome loop can later compare a post-decision measurement against
    the *same* baseline the anomaly was originally judged against.
    """
    props: dict[str, Any] = {
        "title": title,
        "component": component,
        "severity": severity,
    }
    if period:
        props["period_start"] = period[0]
        props["period_end"] = period[1]
    if period_prior:
        props["period_prior_start"] = period_prior[0]
        props["period_prior_end"] = period_prior[1]
    if run_id:
        props["run_id"] = run_id
    if extra:
        props.update(extra)
    return create_node("Insight", external_ref=f"rec:{rec_id}", properties=props)


OUTCOME_MEASUREMENT_DAYS = 30
"""Default window after an approval before we measure the actual effect."""


def record_decision_for_hitl(
    rec_id: str,
    hitl_decision_id: str,
    decision: str,
    approver: str,
    comment: str | None = None,
) -> str | None:
    """Create a Decision node + LED_TO edge from the originating Insight.

    For 'approve' decisions we set `outcome_due_at` so a scheduled job
    (or the manual measure endpoint) can find them once the observation
    window has elapsed.

    Returns the Decision node_id, or None if no matching Insight exists
    (e.g. very-old recommendations created before KG wiring landed).
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT node_id FROM kg.nodes WHERE external_ref = :ref AND label = 'Insight'"),
            {"ref": f"rec:{rec_id}"},
        ).first()
    if not row:
        return None
    insight_id = str(row[0])

    now = datetime.now(UTC)
    properties: dict[str, Any] = {
        "decision": decision,
        "approver": approver,
        "comment": comment,
        "rec_id": rec_id,
        "decided_at": now.isoformat(),
    }
    if decision == "approve":
        properties["outcome_due_at"] = (
            now + timedelta(days=OUTCOME_MEASUREMENT_DAYS)
        ).isoformat()

    decision_node = create_node(
        "Decision",
        external_ref=f"hitl:{hitl_decision_id}",
        properties=properties,
    )
    create_edge(insight_id, decision_node, "LED_TO", properties={"decision": decision})
    return decision_node


def record_evidence_for_causal_estimate(
    rec_id_or_run_id: str,
    component: str,
    estimate: dict[str, Any],
    method: str = "causal_impact",
) -> tuple[str | None, str | None]:
    """Create Hypothesis + Evidence + edges around a causal estimate.

    Returns (hypothesis_id, evidence_id). Both None if no matching Insight
    exists (so this is safe to call even when KG wasn't populated upstream).
    """
    # Locate the Insight either via rec_id or run_id
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT node_id FROM kg.nodes "
                "WHERE label = 'Insight' "
                "  AND (external_ref = :rec_ref OR properties->>'run_id' = :run_id) "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {
                "rec_ref": f"rec:{rec_id_or_run_id}",
                "run_id": rec_id_or_run_id,
            },
        ).first()
    if not row:
        return (None, None)
    insight_id = str(row[0])

    hyp_id = create_node(
        "Hypothesis",
        properties={
            "component": component,
            "summary": f"Treatment on {component} causes the observed effect.",
        },
    )
    create_edge(insight_id, hyp_id, "SUPPORTS")

    rel_effect = estimate.get("rel_effect")
    ci_lo = estimate.get("rel_effect_lower_95ci")
    ci_hi = estimate.get("rel_effect_upper_95ci")
    p = estimate.get("p_value")
    significant = bool(estimate.get("is_significant"))

    evidence_id = create_node(
        "Evidence",
        properties={
            "method": method,
            "rel_effect": rel_effect,
            "p_value": p,
            "is_significant": significant,
            "pre_period": estimate.get("pre_period"),
            "post_period": estimate.get("post_period"),
        },
    )
    create_edge(
        hyp_id,
        evidence_id,
        "BACKS",
        effect_size=rel_effect,
        ci_lower=ci_lo,
        ci_upper=ci_hi,
        method=method,
        confidence=(1 - p) if (p is not None and significant) else None,
    )
    return (hyp_id, evidence_id)


def record_outcome(
    decision_id: str,
    metric: str,
    expected: float | None,
    observed: float | None,
    period: tuple[str, str],
    notes: str | None = None,
) -> str | None:
    """Create an Outcome node + RESULTED_IN edge from a Decision.

    Returns the Outcome node_id, or None if the decision doesn't exist.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT node_id FROM kg.nodes WHERE node_id = :id AND label = 'Decision'"),
            {"id": decision_id},
        ).first()
    if not row:
        return None

    outcome_node = create_node(
        "Outcome",
        properties={
            "metric": metric,
            "expected_effect": expected,
            "observed_effect": observed,
            "period_start": period[0],
            "period_end": period[1],
            "notes": notes,
            "measured_at": datetime.now(UTC).isoformat(),
        },
    )
    create_edge(decision_id, outcome_node, "RESULTED_IN")
    return outcome_node


# ---- Outcome measurement loop ------------------------------------------

# Maps the kpi name stored in an Insight to the SQL bits we need to
# measure its actual value over a post-decision window. Extend this as
# more KPIs participate in the outcome loop.
_OUTCOME_KPI_SQL: dict[str, dict[str, str]] = {
    "conversion_rate": {
        "view": "kpi.conversion_rate_daily",
        "date_col": "day",
        # Aggregate as a rate (conversions / sessions) over the window so a
        # short window with low traffic doesn't get unfairly noisy.
        "rate_expr": "SUM(conversions)::float / NULLIF(SUM(sessions), 0)",
    },
}


def _parse_component(component: str | None) -> tuple[str, str] | None:
    """Turn 'device=mobile' into ('device', 'mobile'). Returns None for free-form."""
    if not component or "=" not in component:
        return None
    field, _, value = component.partition("=")
    field = field.strip()
    value = value.strip()
    if not field or not value:
        return None
    # Whitelist the dimensions we know exist in the KPI views.
    if field not in {"device", "channel", "country", "category", "region"}:
        return None
    return field, value


def _measure_rate(
    cfg: dict[str, str],
    component: tuple[str, str] | None,
    period_start: str,
    period_end: str,
) -> float | None:
    """Run the KPI's rate expression over a given window + optional filter."""
    where = f"{cfg['date_col']} >= :start AND {cfg['date_col']} < :end"
    params: dict[str, Any] = {"start": period_start, "end": period_end}
    if component is not None:
        field, value = component
        where += f" AND {field} = :comp_value"
        params["comp_value"] = value
    sql = text(f"SELECT {cfg['rate_expr']} FROM {cfg['view']} WHERE {where}")
    with engine.connect() as conn:
        result = conn.execute(sql, params).scalar_one_or_none()
    if result is None:
        return None
    return float(result)


def _latest_data_date_for(view: str, date_col: str) -> datetime | None:
    """Anchor for demo data that lives in 2018 — caps the post-window."""
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT MAX({date_col}) FROM {view}")).scalar_one_or_none()
    if result is None:
        return None
    # SQLAlchemy gives us a date; promote to a UTC datetime midnight.
    if hasattr(result, "isoformat"):
        return datetime.fromisoformat(str(result) + "T00:00:00+00:00")
    return None


def measure_outcome_for_decision(
    decision_id: str,
    *,
    post_period_days: int = OUTCOME_MEASUREMENT_DAYS,
    notes: str | None = None,
) -> dict[str, Any]:
    """Read a Decision + its Insight, measure the KPI after the decision,
    and persist an Outcome node.

    Strategy
    --------
    1. Get the Decision's `decided_at` and the parent Insight's
       (kpi, component, baseline-period).
    2. Define post-period:
         start = decided_at
         end   = min(decided_at + post_period_days, last available data point)
    3. Measure the KPI's rate over the post-period.
    4. Compute observed effect vs the baseline rate from the Insight's
       `period_prior` (the same window the original anomaly was
       compared against).
    5. Skip if no Outcome would be meaningful (e.g. <3 days of data) —
       returns {"status": "deferred"} so caller can retry later.
    6. Otherwise persist via record_outcome() and return the result.

    Demo-friendly: for data anchored in 2018 the post-window is capped
    at the last available data point. The caller can override
    `post_period_days` to span the whole available horizon for an
    immediate demo.
    """
    with engine.connect() as conn:
        decision_row = conn.execute(
            text(
                "SELECT node_id, properties FROM kg.nodes "
                "WHERE node_id = :id AND label = 'Decision'"
            ),
            {"id": decision_id},
        ).first()
    if not decision_row:
        return {"status": "error", "error": "decision not found"}
    decision_props: dict[str, Any] = decision_row[1] or {}

    # Already measured?
    with engine.connect() as conn:
        existing = conn.execute(
            text(
                "SELECT n.node_id FROM kg.nodes n "
                "JOIN kg.edges e ON e.to_node = n.node_id "
                "WHERE e.from_node = :did AND e.label = 'RESULTED_IN' "
                "  AND n.label = 'Outcome' "
                "ORDER BY n.created_at DESC LIMIT 1"
            ),
            {"did": decision_id},
        ).first()
    if existing:
        return {"status": "already_measured", "outcome_id": str(existing[0])}

    # Find the upstream Insight via the LED_TO edge.
    with engine.connect() as conn:
        insight_row = conn.execute(
            text(
                "SELECT n.node_id, n.properties FROM kg.nodes n "
                "JOIN kg.edges e ON e.from_node = n.node_id "
                "WHERE e.to_node = :did AND e.label = 'LED_TO' "
                "  AND n.label = 'Insight' "
                "LIMIT 1"
            ),
            {"did": decision_id},
        ).first()
    if not insight_row:
        return {"status": "error", "error": "no upstream insight for this decision"}
    insight_props: dict[str, Any] = insight_row[1] or {}

    kpi = insight_props.get("kpi")
    cfg = _OUTCOME_KPI_SQL.get(str(kpi) if kpi else "")
    if cfg is None:
        return {
            "status": "unsupported_kpi",
            "kpi": kpi,
            "supported": list(_OUTCOME_KPI_SQL.keys()),
        }
    component = _parse_component(insight_props.get("component"))

    # Define the measurement window.
    try:
        decided_at = datetime.fromisoformat(decision_props["decided_at"].replace("Z", "+00:00"))
    except Exception:
        return {"status": "error", "error": "decision.decided_at unreadable"}

    naive_end = decided_at + timedelta(days=int(post_period_days))
    horizon = _latest_data_date_for(cfg["view"], cfg["date_col"])
    if horizon is not None and horizon < decided_at:
        # Demo-data quirk: data window is in 2018 but decisions are in
        # 2026. Slide the post-period to the tail of the data so the
        # user sees a real, comparable measurement instead of "0 rows".
        end_dt = horizon
        start_dt = end_dt - timedelta(days=int(post_period_days))
        anchored_to_data = True
    else:
        end_dt = min(naive_end, horizon) if horizon is not None else naive_end
        start_dt = decided_at
        anchored_to_data = False

    if (end_dt - start_dt).days < 3:
        return {
            "status": "deferred",
            "reason": "less than 3 days of post-period data available",
            "next_check_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
        }

    period_start = start_dt.date().isoformat()
    period_end = end_dt.date().isoformat()

    observed_rate = _measure_rate(cfg, component, period_start, period_end)

    # Baseline rate from the Insight's prior period (the "healthy" reference).
    baseline_start = insight_props.get("period_prior_start") or insight_props.get(
        "period_start"
    )
    baseline_end = insight_props.get("period_prior_end") or insight_props.get("period_end")
    baseline_rate: float | None = None
    if baseline_start and baseline_end:
        baseline_rate = _measure_rate(cfg, component, baseline_start, baseline_end)

    if observed_rate is None:
        return {
            "status": "deferred",
            "reason": "no rows in measurement window",
            "period": [period_start, period_end],
        }

    observed_effect: float | None = None
    if baseline_rate is not None and baseline_rate > 0:
        observed_effect = (observed_rate - baseline_rate) / baseline_rate

    expected_effect = insight_props.get("relative_change")
    try:
        expected_effect = float(expected_effect) if expected_effect is not None else None
    except (TypeError, ValueError):
        expected_effect = None

    auto_notes = notes
    if auto_notes is None:
        parts = []
        if anchored_to_data:
            parts.append("post-Periode an Datenhorizont gerichtet (Demo-Anker 2018)")
        parts.append(f"Baseline (Insight period_prior): {baseline_rate}")
        parts.append(f"Beobachtet: {observed_rate}")
        auto_notes = " · ".join(parts)

    outcome_id = record_outcome(
        decision_id=decision_id,
        metric=str(kpi),
        expected=expected_effect,
        observed=observed_effect,
        period=(period_start, period_end),
        notes=auto_notes,
    )
    if outcome_id is None:
        return {"status": "error", "error": "outcome insert failed"}

    return {
        "status": "measured",
        "outcome_id": outcome_id,
        "decision_id": decision_id,
        "metric": kpi,
        "component": insight_props.get("component"),
        "period_start": period_start,
        "period_end": period_end,
        "observed_rate": observed_rate,
        "baseline_rate": baseline_rate,
        "expected_effect": expected_effect,
        "observed_effect": observed_effect,
        "anchored_to_data": anchored_to_data,
    }


def find_decisions_due_for_outcome(*, limit: int = 50) -> list[dict[str, Any]]:
    """All approved Decisions whose outcome_due_at has passed and which
    don't yet have a connected Outcome node.

    Use this from a scheduled job (n8n cron) or a manual cleanup pass.
    """
    sql = text(
        "SELECT d.node_id, d.properties "
        "FROM kg.nodes d "
        "WHERE d.label = 'Decision' "
        "  AND (d.properties->>'decision') = 'approve' "
        "  AND (d.properties->>'outcome_due_at')::timestamptz < now() "
        "  AND NOT EXISTS ( "
        "    SELECT 1 FROM kg.edges e "
        "    JOIN kg.nodes o ON o.node_id = e.to_node "
        "    WHERE e.from_node = d.node_id "
        "      AND e.label = 'RESULTED_IN' "
        "      AND o.label = 'Outcome' "
        "  ) "
        "ORDER BY d.created_at "
        "LIMIT :limit"
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"limit": limit}).fetchall()
    return [
        {"decision_id": str(r[0]), "properties": (r[1] or {})}
        for r in rows
    ]
