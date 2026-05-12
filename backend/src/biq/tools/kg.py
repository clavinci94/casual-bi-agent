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
from datetime import datetime
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

    sql = text(
        "SELECT n.node_id, n.external_ref, n.properties, n.created_at "
        "FROM kg.nodes n "
        "LEFT JOIN audit.agent_runs ar "
        "  ON ar.run_id = (n.properties->>'run_id') "
        "WHERE n.label = 'Insight' "
        f"{where_extra} "
        "ORDER BY n.created_at DESC LIMIT :limit"
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, params).all()
    return [
        {
            "insight_id": r[0],
            "external_ref": r[1],
            "properties": r[2],
            "created_at": r[3],
        }
        for r in rows
    ]


# ---- Domain-specific helpers used by the wiring ------------------------


def record_insight_for_recommendation(
    rec_id: str,
    title: str,
    component: str | None = None,
    severity: str | None = None,
    period: tuple[str, str] | None = None,
    run_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Create an Insight node for a freshly-logged recommendation."""
    props: dict[str, Any] = {
        "title": title,
        "component": component,
        "severity": severity,
    }
    if period:
        props["period_start"] = period[0]
        props["period_end"] = period[1]
    if run_id:
        props["run_id"] = run_id
    if extra:
        props.update(extra)
    return create_node("Insight", external_ref=f"rec:{rec_id}", properties=props)


def record_decision_for_hitl(
    rec_id: str,
    hitl_decision_id: str,
    decision: str,
    approver: str,
    comment: str | None = None,
) -> str | None:
    """Create a Decision node + LED_TO edge from the originating Insight.

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

    decision_node = create_node(
        "Decision",
        external_ref=f"hitl:{hitl_decision_id}",
        properties={
            "decision": decision,
            "approver": approver,
            "comment": comment,
            "rec_id": rec_id,
            "decided_at": datetime.utcnow().isoformat(),
        },
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
            "measured_at": datetime.utcnow().isoformat(),
        },
    )
    create_edge(decision_id, outcome_node, "RESULTED_IN")
    return outcome_node
