"""KPI views should aggregate the simulated data into the expected shape."""

from __future__ import annotations

from sqlalchemy import text

from biq.db import engine
from biq.tools.kpi import ALLOWED_VIEWS


def test_all_views_exist(db_ready: bool) -> None:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name FROM information_schema.views "
                "WHERE table_schema = 'kpi'"
            )
        ).all()
    found = {r[0] for r in rows}
    assert ALLOWED_VIEWS <= found, f"missing views: {ALLOWED_VIEWS - found}"


def test_conversion_rate_daily_has_data(db_ready: bool) -> None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT count(*), sum(sessions), sum(conversions) "
                "FROM kpi.conversion_rate_daily"
            )
        ).one()
    n_rows, sessions, conversions = row
    assert n_rows > 0, "conversion_rate_daily empty"
    assert sessions > 0
    assert conversions > 0
    assert conversions < sessions, "conversions cannot exceed sessions"


def test_mobile_drops_in_bug_window(db_ready: bool) -> None:
    """The simulator's rel_mobile_v2 regression should be visible at the view level."""
    sql = text(
        "SELECT device, "
        "       ROUND(100.0 * SUM(conversions)::numeric / NULLIF(SUM(sessions), 0), 2) "
        "         AS conv_pct "
        "FROM kpi.conversion_rate_daily "
        "WHERE day >= :start AND day < :end "
        "GROUP BY device"
    )

    with engine.connect() as conn:
        pre = {
            r[0]: float(r[1])
            for r in conn.execute(sql, {"start": "2018-03-10", "end": "2018-04-07"}).all()
        }
        post = {
            r[0]: float(r[1])
            for r in conn.execute(sql, {"start": "2018-04-15", "end": "2018-05-10"}).all()
        }

    mobile_drop = (post["mobile"] - pre["mobile"]) / pre["mobile"]
    desktop_drop = (post["desktop"] - pre["desktop"]) / pre["desktop"]

    # Mobile should drop substantially; desktop barely moves.
    assert mobile_drop < -0.20, f"expected mobile drop > 20%, got {mobile_drop:.2%}"
    assert abs(desktop_drop) < 0.10, f"desktop should be ~flat, got {desktop_drop:.2%}"


def test_repeat_purchase_rate_in_bounds(db_ready: bool) -> None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT min(repeat_rate_pct), max(repeat_rate_pct) "
                "FROM kpi.repeat_purchase_rate"
            )
        ).one()
    if row[0] is None:
        return  # cohort might be empty in extreme test fixtures
    assert 0 <= float(row[0]) <= 100
    assert 0 <= float(row[1]) <= 100
