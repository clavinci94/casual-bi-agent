"""Causal inference tool. Fetches daily series from kpi.conversion_rate_daily,
calls the R Plumber service running CausalImpact, returns the effect estimate
with confidence interval and p-value.

The R service is intentionally stateless: Python owns the data access (via the
governed kpi.* semantic layer), R owns the statistics. Same MCP everywhere
pattern as the rest of the project.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import httpx
import pandas as pd
from sqlalchemy import text

from biq.db import engine

R_BASE_URL = os.environ.get("R_BASE_URL", "http://localhost:8765")
_TIMEOUT_S = 120.0


def _date(s: str | date) -> date:
    return s if isinstance(s, date) else date.fromisoformat(s)


def _fetch_conversion_series(start: date, end: date, devices: list[str]) -> pd.DataFrame:
    """Daily conv-rate per device from kpi.conversion_rate_daily.

    Returns a wide frame indexed by day with one column per device.
    """
    sql = text(
        "SELECT day, device, SUM(sessions)::int AS sessions, "
        "       SUM(conversions)::int AS conversions "
        "FROM kpi.conversion_rate_daily "
        "WHERE day >= :start AND day <= :end AND device = ANY(:devices) "
        "GROUP BY day, device "
        "ORDER BY day, device"
    )
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"start": start, "end": end, "devices": list(devices)})
    if df.empty:
        return df

    df["conv_rate"] = df["conversions"] / df["sessions"].replace(0, 1)
    return (
        df.pivot_table(index="day", columns="device", values="conv_rate")
        .sort_index()
        .ffill()
        .fillna(0)
    )


def causal_impact_conversion(
    target_device: str,
    pre_start: str,
    pre_end: str,
    post_start: str,
    post_end: str,
    controls: list[str] | None = None,
) -> dict[str, Any]:
    """Estimate the causal effect of a treatment on a device's conversion rate.

    Uses CausalImpact (Bayesian structural time series) with optional synthetic
    control from other devices.

    Args:
        target_device: 'mobile' | 'desktop' | 'tablet'
        pre_start, pre_end: ISO dates of the pre-period (inclusive).
        post_start, post_end: ISO dates of the post-period (inclusive).
        controls: optional list of other devices to use as controls.

    Returns:
        Dict with rel_effect / rel_effect_lower / rel_effect_upper (95% CI),
        p_value, is_significant, and metadata about the run.
    """
    devices = [target_device] + (controls or [])
    pre_s, pre_e = _date(pre_start), _date(pre_end)
    post_s, post_e = _date(post_start), _date(post_end)

    wide = _fetch_conversion_series(pre_s, post_e, devices)
    if wide.empty or target_device not in wide.columns:
        return {"error": f"no data for target_device={target_device} in window"}

    body: dict[str, Any] = {
        "y": wide[target_device].tolist(),
        "dates": [d.isoformat() for d in wide.index],
        "pre_period": [pre_s.isoformat(), pre_e.isoformat()],
        "post_period": [post_s.isoformat(), post_e.isoformat()],
    }
    if controls:
        body["X"] = {c: wide[c].tolist() for c in controls if c in wide.columns}

    resp = httpx.post(f"{R_BASE_URL}/causal-impact", json=body, timeout=_TIMEOUT_S)
    if resp.status_code != 200:
        return {
            "error": f"r-service returned {resp.status_code}",
            "detail": resp.text[:500],
        }

    payload = resp.json()
    summary = payload.get("summary", {})

    return {
        "target_device": target_device,
        "controls_used": list(body.get("X", {}).keys()),
        "rel_effect": _scalar(summary.get("rel_effect")),
        "rel_effect_lower_95ci": _scalar(summary.get("rel_effect_lower")),
        "rel_effect_upper_95ci": _scalar(summary.get("rel_effect_upper")),
        "abs_effect": _scalar(summary.get("abs_effect")),
        "p_value": _scalar(summary.get("p_value")),
        "is_significant": _scalar(summary.get("is_significant")),
        "avg_actual": _scalar(summary.get("avg_actual")),
        "avg_predicted": _scalar(summary.get("avg_predicted")),
        "n_observations": payload.get("n_observations"),
        "pre_period": payload.get("pre_period"),
        "post_period": payload.get("post_period"),
    }


def _scalar(x: Any) -> Any:
    """Plumber wraps single scalars as one-element arrays in JSON. Unwrap them."""
    if isinstance(x, list) and len(x) == 1:
        return x[0]
    return x


def health() -> dict[str, Any]:
    """Ping the R service. Returns its (unwrapped) health payload or an error."""
    try:
        resp = httpx.get(f"{R_BASE_URL}/health", timeout=5.0)
        resp.raise_for_status()
        return {k: _scalar(v) for k, v in resp.json().items()}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
