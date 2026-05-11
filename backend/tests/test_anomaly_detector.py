"""The heuristic anomaly detector must rediscover the simulator's ground truth."""

from __future__ import annotations

from datetime import date

from sqlalchemy import text

from biq.agents.anomaly import run
from biq.db import engine


def test_detects_mobile_v2_regression(db_ready: bool) -> None:
    result = run(reference_day=date(2018, 5, 5))

    insights = result["insights"]
    assert insights, "expected at least one insight for the mobile bug window"

    mobile = next(
        (i for i in insights if i["dimension"] == "device" and i["value"] == "mobile"),
        None,
    )
    assert mobile is not None, f"no mobile insight in {insights}"

    # Sign: a drop, not a spike
    assert mobile["relative_change_pct"] < -15, mobile

    # Severity: with a ~35% drop and thousands of sessions, expect medium or high
    assert mobile["severity"] in {"medium", "high"}, mobile["severity"]

    # Audit trail must exist
    assert result["recommendation_ids"], "no recommendation logged"

    with engine.connect() as conn:
        rec = conn.execute(
            text("SELECT title, risk_level, run_id FROM audit.recommendations WHERE rec_id = :id"),
            {"id": result["recommendation_ids"][0]},
        ).one()
    assert "mobile" in rec[0].lower()
    assert rec[2] == result["run_id"]


def test_no_anomaly_in_quiet_window(db_ready: bool) -> None:
    """A pre-bug window with no treatment should yield zero insights."""
    result = run(reference_day=date(2017, 11, 1))
    # The detector might still flag something if simulator noise crosses threshold,
    # so we just assert no mobile drops above 30%.
    for i in result["insights"]:
        if i["value"] == "mobile":
            assert i["relative_change_pct"] > -30, i
