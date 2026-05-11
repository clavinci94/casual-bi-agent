"""Context lookups: releases and campaigns active in a time window.

These are candidate-treatment finders for causal investigations: when a
KPI moves, the agent checks what releases or campaigns were live at the
time, then asks the causal layer to estimate an effect.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
from sqlalchemy import text

from biq.db import engine


def _df_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """to_dict variant that round-trips through JSON so datetimes etc become strings."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


def releases_in_window(start: str, end: str) -> dict[str, Any]:
    """Software releases overlapping [start, end)."""
    sql = text(
        "SELECT release_id, component, version, released_ts, rollback_ts, notes "
        "FROM raw.releases "
        "WHERE released_ts < :end "
        "  AND (rollback_ts IS NULL OR rollback_ts >= :start) "
        "ORDER BY released_ts"
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"start": start, "end": end})
    return {"rows": _df_to_records(df), "row_count": int(len(df))}


def campaigns_in_window(start: str, end: str) -> dict[str, Any]:
    """Marketing campaigns overlapping [start, end)."""
    sql = text(
        "SELECT campaign_id, name, channel, target_segment, target_region, "
        "       start_ts, end_ts, budget_brl, hypothesis "
        "FROM raw.campaigns "
        "WHERE start_ts < :end "
        "  AND (end_ts IS NULL OR end_ts >= :start) "
        "ORDER BY start_ts"
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"start": start, "end": end})
    return {"rows": _df_to_records(df), "row_count": int(len(df))}
