"""Read tools against the kpi.* semantic layer.

Used by both heuristic agents (called directly) and the LLM investigator
(exposed as a Claude tool). Will later be wrapped as an MCP server so
external LLMs can also reach it.
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


ALLOWED_VIEWS: set[str] = {
    "conversion_rate_daily",
    "aov_daily",
    "gross_margin_weekly",
    "delivery_time_p95",
    "review_score_avg",
    "refund_rate",
    "repeat_purchase_rate",
    "churn_30d",
}

# Views whose primary date column is `day` (rest use `week`).
DAY_VIEWS: set[str] = {"conversion_rate_daily", "aov_daily", "delivery_time_p95"}


def _date_col(view: str) -> str:
    return "day" if view in DAY_VIEWS else "week"


def kpi_query(
    view: str,
    start: str,
    end: str,
    group_by: list[str] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """SELECT from kpi.<view> for date range [start, end).

    If group_by is given, aggregates numeric columns by those dimensions.
    Returns up to `limit` rows.
    """
    if view not in ALLOWED_VIEWS:
        return {"error": f"view '{view}' not allowed", "allowed": sorted(ALLOWED_VIEWS)}

    date_col = _date_col(view)
    sql = text(
        f"SELECT * FROM kpi.{view} "
        f"WHERE {date_col} >= :start AND {date_col} < :end "
        f"ORDER BY {date_col}"
    )

    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"start": start, "end": end})

    if df.empty:
        return {"rows": [], "row_count": 0, "note": "no data for window"}

    if group_by:
        valid = [d for d in group_by if d in df.columns]
        if valid:
            numeric = df.select_dtypes(include="number").columns.tolist()
            # Pre-computed ratios/percentiles cannot be summed — drop them when
            # aggregating. Counts/sums (sessions, conversions, revenue) remain.
            summable = [
                c
                for c in numeric
                if not (
                    c.endswith("_pct")
                    or c.endswith("_rate")
                    or c.endswith("_avg")
                    or c.startswith("avg_")
                    or c.startswith("p95_")
                    or c == "gross_margin"
                )
            ]
            df = df.groupby(valid, as_index=False, dropna=False)[summable].sum()

    return {
        "rows": _df_to_records(df.head(limit)),
        "row_count": len(df),
        "columns": list(df.columns),
        "truncated": bool(len(df) > limit),
    }
