"""Knowledge-graph wiring tests: every recommendation creates an Insight,
HITL approval creates a Decision, lookup returns the linked history.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from biq.api.app import app
from biq.audit import log_recommendation, run_context
from biq.db import engine
from biq.tools import kg as kg_tools

client = TestClient(app)


# ---- Node + edge primitives -------------------------------------------


def test_create_node_idempotent_on_external_ref(db_ready: bool) -> None:
    a = kg_tools.create_node("Customer", external_ref="kg-test-cust-1", properties={"x": 1})
    b = kg_tools.create_node("Customer", external_ref="kg-test-cust-1", properties={"x": 2})
    assert a == b  # same ref returns same node_id


def test_create_edge(db_ready: bool) -> None:
    n1 = kg_tools.create_node("Insight", external_ref="kg-test-edge-1")
    n2 = kg_tools.create_node("Decision", external_ref="kg-test-edge-2")
    edge_id = kg_tools.create_edge(n1, n2, "LED_TO", effect_size=-0.4, method="causal_impact")
    assert edge_id

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT label, effect_size, method FROM kg.edges WHERE edge_id = :id"),
            {"id": edge_id},
        ).one()
    assert row[0] == "LED_TO"
    assert float(row[1]) == -0.4
    assert row[2] == "causal_impact"


# ---- Auto-creation hooks ---------------------------------------------


def test_recommendation_mirrors_to_insight(db_ready: bool) -> None:
    with run_context(trigger="test", prompt="kg insight test") as ctx:
        rec_id = log_recommendation(
            run_id=ctx.run_id,
            title="kg test insight",
            body="body mentioning mobile",
            confidence=0.7,
            action_type="read_only",
            risk_level="medium",
            component="mobile_checkout",
            period=("2018-04-15", "2018-05-10"),
        )

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT label, properties FROM kg.nodes WHERE external_ref = :ref"),
            {"ref": f"rec:{rec_id}"},
        ).one()
    assert row[0] == "Insight"
    props = row[1]
    assert props["component"] == "mobile_checkout"
    assert props["severity"] == "medium"
    assert props["period_start"] == "2018-04-15"


def test_hitl_decision_mirrors_to_kg_decision(db_ready: bool) -> None:
    # Create rec → insight
    with run_context(trigger="test", prompt="kg decision test") as ctx:
        rec_id = log_recommendation(
            run_id=ctx.run_id,
            title="kg decision test",
            body="body mentioning checkout",
            confidence=0.5,
            action_type="read_only",
            risk_level="low",
            component="mobile_checkout",
        )

    # Approve via API
    r = client.post(
        f"/api/recommendations/{rec_id}/decision",
        json={"decision": "approve", "approver": "kg-test"},
    )
    assert r.status_code == 200

    # Insight node exists
    with engine.connect() as conn:
        insight_id = conn.execute(
            text("SELECT node_id FROM kg.nodes WHERE external_ref = :ref"),
            {"ref": f"rec:{rec_id}"},
        ).scalar_one()

        # Decision node exists and is linked via LED_TO
        edge = conn.execute(
            text(
                "SELECT e.to_node, n.label, n.properties "
                "FROM kg.edges e JOIN kg.nodes n ON n.node_id = e.to_node "
                "WHERE e.from_node = :insight AND e.label = 'LED_TO'"
            ),
            {"insight": str(insight_id)},
        ).one()
    assert edge[1] == "Decision"
    assert edge[2]["decision"] == "approve"
    assert edge[2]["approver"] == "kg-test"


# ---- Outcome + lookup -------------------------------------------------


def test_record_outcome_creates_node_and_edge(db_ready: bool) -> None:
    # Build a decision node manually
    insight = kg_tools.create_node(
        "Insight",
        external_ref="kg-outcome-test-rec",
        properties={"component": "checkout"},
    )
    decision = kg_tools.create_node(
        "Decision",
        external_ref="kg-outcome-test-dec",
        properties={"decision": "approve", "approver": "test"},
    )
    kg_tools.create_edge(insight, decision, "LED_TO")

    outcome_id = kg_tools.record_outcome(
        decision_id=decision,
        metric="conversion_rate",
        expected=0.40,
        observed=0.38,
        period=("2018-05-15", "2018-05-22"),
        notes="rollback validated",
    )
    assert outcome_id

    with engine.connect() as conn:
        node = conn.execute(
            text("SELECT label, properties FROM kg.nodes WHERE node_id = :id"),
            {"id": outcome_id},
        ).one()
    assert node[0] == "Outcome"
    assert node[1]["metric"] == "conversion_rate"
    assert float(node[1]["observed_effect"]) == 0.38


def test_lookup_finds_past_decisions(db_ready: bool) -> None:
    # Set up: insight → decision → outcome for component 'kg-lookup-test'
    with run_context(trigger="test", prompt="kg lookup test") as ctx:
        rec_id = log_recommendation(
            run_id=ctx.run_id,
            title="kg lookup test",
            body="body",
            confidence=0.7,
            action_type="read_only",
            risk_level="high",
            component="kg-lookup-test",
        )

    client.post(
        f"/api/recommendations/{rec_id}/decision",
        json={"decision": "approve", "approver": "tester"},
    )

    result = kg_tools.lookup_past_decisions("kg-lookup-test", days_back=30)
    assert result["n_insights"] >= 1
    assert result["n_decided"] >= 1
    # The latest insight should be the one we just created
    titles = [i["insight"].get("title") for i in result["insights"]]
    assert "kg lookup test" in titles


# ---- API endpoints ----------------------------------------------------


def test_kg_insights_endpoint(db_ready: bool) -> None:
    r = client.get("/api/kg/insights?limit=5")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_kg_learnings_endpoint(db_ready: bool) -> None:
    r = client.get("/api/kg/learnings/mobile_checkout?days_back=30")
    assert r.status_code == 200
    body = r.json()
    assert body["component"] == "mobile_checkout"
    assert "insights" in body
    assert "n_insights" in body


def test_kg_outcomes_endpoint_404_on_unknown_decision(db_ready: bool) -> None:
    r = client.post(
        "/api/kg/outcomes",
        json={
            "decision_id": "no-such-decision",
            "metric": "conversion_rate",
            "period_start": "2018-05-15",
            "period_end": "2018-05-22",
        },
    )
    assert r.status_code == 404
