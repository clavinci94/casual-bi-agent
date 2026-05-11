"""Unit tests for biq.agents.graph nodes.

Tests exercise individual nodes with fabricated states so the LangGraph
flow is fully covered without needing the R service. The full end-to-end
graph run is exercised in test_anomaly_detector / make graph-investigate.
"""

from __future__ import annotations

from sqlalchemy import text

from biq.agents import graph as gmod
from biq.db import engine

# --- Pure / fast tests (no DB) ------------------------------------------


def test_pick_treatment_prefers_rolled_back() -> None:
    treatments = [
        {
            "release_id": "rel_a",
            "component": "mobile_checkout",
            "version": "v1.0",
            "released_ts": "2018-01-01T00:00:00Z",
            "rollback_ts": None,
        },
        {
            "release_id": "rel_b",
            "component": "mobile_checkout",
            "version": "v2.0",
            "released_ts": "2018-04-15T00:00:00Z",
            "rollback_ts": "2018-05-10T00:00:00Z",
        },
    ]
    out = gmod._pick_treatment(treatments, "mobile", "2018-04-15")
    assert "rel_b" in out
    assert "v2.0" in out


def test_pick_treatment_picks_latest_when_no_rollback() -> None:
    treatments = [
        {
            "release_id": "rel_a",
            "component": "mobile_checkout",
            "version": "v1.0",
            "released_ts": "2018-01-01T00:00:00Z",
            "rollback_ts": None,
        },
        {
            "release_id": "rel_c",
            "component": "mobile_checkout",
            "version": "v3.0",
            "released_ts": "2018-03-15T00:00:00Z",
            "rollback_ts": None,
        },
    ]
    out = gmod._pick_treatment(treatments, "mobile", "2018-04-15")
    assert "rel_c" in out


def test_pick_treatment_no_match_returns_fallback() -> None:
    treatments = [
        {
            "release_id": "rel_x",
            "component": "search",
            "version": "v1.0",
            "released_ts": "2018-01-01",
            "rollback_ts": None,
        },
    ]
    out = gmod._pick_treatment(treatments, "mobile", "2018-04-15")
    assert "No device-specific release" in out


def test_narrative_high_confidence_path() -> None:
    state = {
        "target_device": "mobile",
        "post_period": ("2018-04-15", "2018-05-10"),
        "treatments": [],
        "causal_estimate": {
            "rel_effect": -0.40,
            "p_value": 0.001,
            "rel_effect_lower_95ci": -0.45,
            "rel_effect_upper_95ci": -0.35,
            "is_significant": True,
        },
    }
    out = gmod.narrative_node(state)  # type: ignore[arg-type]
    assert out["risk_level"] == "high"
    assert out["confidence"] >= 0.8
    assert "mobile" in out["finding_body"]
    assert "p =" in out["finding_body"]
    assert "40.0%" in out["finding_title"]


def test_narrative_low_confidence_path() -> None:
    state = {
        "target_device": "mobile",
        "post_period": ("2018-04-15", "2018-05-10"),
        "treatments": [],
        "causal_estimate": {
            "rel_effect": -0.05,
            "p_value": 0.30,
            "rel_effect_lower_95ci": -0.10,
            "rel_effect_upper_95ci": 0.00,
            "is_significant": False,
        },
    }
    out = gmod.narrative_node(state)  # type: ignore[arg-type]
    assert out["risk_level"] == "low"
    assert out["confidence"] < 0.5


def test_narrative_handles_missing_estimate() -> None:
    state = {
        "target_device": "mobile",
        "post_period": ("2018-04-15", "2018-05-10"),
        "treatments": [],
        "causal_estimate": {"error": "r-service unreachable"},
    }
    out = gmod.narrative_node(state)  # type: ignore[arg-type]
    assert out["risk_level"] == "low"
    assert "could not produce" in out["finding_body"]


def test_review_passes_clean_high_finding() -> None:
    state = {
        "target_device": "mobile",
        "risk_level": "high",
        "finding_body": "mobile conversion fell. p = 0.001. significant.",
        "causal_estimate": {"is_significant": True},
        "retries": 0,
    }
    out = gmod.review_node(state)  # type: ignore[arg-type]
    assert out["review_passed"] is True
    assert out["review_comments"] == []


def test_review_rejects_high_without_pvalue() -> None:
    state = {
        "target_device": "mobile",
        "risk_level": "high",
        "finding_body": "mobile conversion fell.",  # no "p ="
        "causal_estimate": {"is_significant": True},
        "retries": 0,
    }
    out = gmod.review_node(state)  # type: ignore[arg-type]
    assert out["review_passed"] is False
    assert any("p-value" in c for c in out["review_comments"])


def test_review_rejects_high_without_significance() -> None:
    state = {
        "target_device": "mobile",
        "risk_level": "high",
        "finding_body": "mobile conversion fell. p = 0.30.",
        "causal_estimate": {"is_significant": False},
        "retries": 0,
    }
    out = gmod.review_node(state)  # type: ignore[arg-type]
    assert out["review_passed"] is False
    assert any("not statistically significant" in c for c in out["review_comments"])


def test_review_rejects_when_body_misses_device() -> None:
    state = {
        "target_device": "tablet",
        "risk_level": "low",
        "finding_body": "no anomaly",  # no "tablet"
        "causal_estimate": {},
        "retries": 0,
    }
    out = gmod.review_node(state)  # type: ignore[arg-type]
    assert out["review_passed"] is False
    assert any("does not mention target device" in c for c in out["review_comments"])


def test_route_after_review_record_when_passed() -> None:
    assert gmod._route_after_review({"review_passed": True, "retries": 1}) == "record"


def test_route_after_review_retries_then_ends() -> None:
    assert gmod._route_after_review({"review_passed": False, "retries": 1}) == "narrative"
    assert gmod._route_after_review({"review_passed": False, "retries": 2}) == "end"


# --- DB-bound node tests ------------------------------------------------


def test_data_node_finds_mobile_drop(db_ready: bool) -> None:
    state = {
        "pre_period": ("2018-02-15", "2018-04-14"),
        "post_period": ("2018-04-15", "2018-05-10"),
        "target_device": "mobile",
    }
    out = gmod.data_node(state)  # type: ignore[arg-type]
    anomalies = out["anomalies"]
    assert anomalies, "data_node should surface at least one anomaly"
    mobile = next((a for a in anomalies if a["device"] == "mobile"), None)
    assert mobile is not None
    assert mobile["rel_change"] < -0.10


def test_context_node_returns_treatments(db_ready: bool) -> None:
    out = gmod.context_node({"post_period": ("2018-04-15", "2018-05-10")})  # type: ignore[arg-type]
    treatments = out["treatments"]
    release_ids = [t.get("release_id") for t in treatments if "release_id" in t]
    assert "rel_mobile_v2" in release_ids


def test_record_node_writes_recommendation(db_ready: bool) -> None:
    # Create a run row first so the FK to audit.recommendations.run_id holds.
    from biq.audit import run_context

    with run_context(trigger="test", prompt="record_node smoke") as ctx:
        state = {
            "run_id": ctx.run_id,
            "finding_title": "test finding",
            "finding_body": "body referencing mobile",
            "confidence": 0.5,
            "risk_level": "low",
        }
        out = gmod.record_node(state)  # type: ignore[arg-type]
        rec_id = out["rec_id"]
        assert rec_id

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT title FROM audit.recommendations WHERE rec_id = :id"),
            {"id": rec_id},
        ).one()
    assert row[0] == "test finding"


def test_build_graph_compiles() -> None:
    g = gmod.build_graph()
    assert g is not None
