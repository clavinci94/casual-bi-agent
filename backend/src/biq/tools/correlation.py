"""Correlation analysis: own-shop KPI vs. an external time series.

Answers the manager question "is our recent revenue dip just the SMI
moving with us, or is it something we did?" by computing Pearson and
Spearman coefficients (with p-values) on aligned daily/weekly series,
then asking Claude for a 2-3-sentence interpretation that a non-stats
reader can act on.

The math is intentionally conservative:
- We never claim causation from correlation. The narrative prompt
  hammers this point.
- We surface n (number of aligned observations) so the reader can see
  whether a "significant" p-value is on 8 points or 80.
- We surface both Pearson and Spearman. Disagreement (e.g. Spearman
  strong, Pearson weak) is itself signal — flagged by the narrative.

Supported INTERNAL series:
    shopify_revenue       — daily revenue across all channels
    shopify_orders        — daily orders across all channels
    shopify_aov           — daily AOV (revenue / orders, across channels)
    shopify_revenue_mobile, *_desktop, *_pos
    shopify_orders_mobile, *_desktop, *_pos

Supported EXTERNAL series:
    market:<symbol>       — yfinance symbol, e.g. market:EURCHF=X
    trends:<keyword>      — Google Trends keyword (weekly granularity)
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd
from anthropic import Anthropic
from scipy import stats
from sqlalchemy import text

from biq.config import settings
from biq.db import engine
from biq.tools.external import market_snapshot, trends_query

_logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # cheap; this is a short narrative

# Maps short internal series names → SQL templates. Channel is optional.
_INTERNAL_QUERIES: dict[str, dict[str, Any]] = {
    "shopify_revenue": {
        "label": "Tagesumsatz (alle Kanäle)",
        "unit": "CHF",
        "sql": """
            SELECT day, SUM(revenue)::float8 AS value
            FROM kpi.shopify_orders_daily
            WHERE day >= :start AND day < :end
            GROUP BY day ORDER BY day
        """,
    },
    "shopify_orders": {
        "label": "Bestellungen / Tag (alle Kanäle)",
        "unit": "Bestellungen",
        "sql": """
            SELECT day, SUM(orders_completed)::float8 AS value
            FROM kpi.shopify_orders_daily
            WHERE day >= :start AND day < :end
            GROUP BY day ORDER BY day
        """,
    },
    "shopify_aov": {
        "label": "Durchschnittlicher Bestellwert / Tag",
        "unit": "CHF",
        "sql": """
            SELECT day,
                   (SUM(revenue) / NULLIF(SUM(orders_completed), 0))::float8 AS value
            FROM kpi.shopify_orders_daily
            WHERE day >= :start AND day < :end
            GROUP BY day ORDER BY day
        """,
    },
}

# Per-channel variants are generated on the fly to avoid 12 boilerplate dict entries.
_CHANNELS = ("mobile", "desktop", "pos", "other")


def _channel_series(metric: str, channel: str) -> dict[str, Any]:
    metric_col = {"revenue": "revenue", "orders": "orders_completed"}[metric]
    label_metric = {"revenue": "Umsatz", "orders": "Bestellungen"}[metric]
    unit = "CHF" if metric == "revenue" else "Bestellungen"
    return {
        "label": f"{label_metric} / Tag ({channel.capitalize()})",
        "unit": unit,
        "sql": f"""
            SELECT day, SUM({metric_col})::float8 AS value
            FROM kpi.shopify_orders_daily
            WHERE day >= :start AND day < :end AND channel = '{channel}'
            GROUP BY day ORDER BY day
        """,
    }


def _resolve_internal(name: str) -> dict[str, Any]:
    if name in _INTERNAL_QUERIES:
        return _INTERNAL_QUERIES[name]
    for ch in _CHANNELS:
        for metric in ("revenue", "orders"):
            if name == f"shopify_{metric}_{ch}":
                return _channel_series(metric, ch)
    raise ValueError(f"unknown internal series: {name}")


# ---------------------------------------------------------------------
# Series fetchers
# ---------------------------------------------------------------------


def _fetch_internal(name: str, start: date, end: date) -> pd.DataFrame:
    spec = _resolve_internal(name)
    sql = text(spec["sql"])
    with engine.connect() as conn:
        rows = conn.execute(sql, {"start": start, "end": end}).all()
    df = pd.DataFrame(rows, columns=["date", "value"])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    return df


def _fetch_external(kind: str, key: str, days: int) -> tuple[pd.DataFrame, str]:
    """Returns (df with date+value columns, friendly label)."""
    if kind == "market":
        period = "1mo" if days <= 35 else "3mo" if days <= 95 else "1y"
        payload = market_snapshot(symbols=[key], period=period)
        items = payload.get("items") or []
        if not items:
            return pd.DataFrame(columns=["date", "value"]), key
        hist = items[0].get("history") or []
        df = pd.DataFrame(hist)
        if df.empty:
            return df, items[0].get("name") or key
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        df = df.rename(columns={"close": "value"})[["date", "value"]]
        return df, items[0].get("name") or key

    if kind == "trends":
        timeframe = "today 3-m" if days <= 95 else "today 12-m"
        payload = trends_query(keywords=[key], geo="CH", timeframe=timeframe)
        timeline = payload.get("timeline") or []
        rows = [
            {"date": pd.to_datetime(p.get("date")).normalize(), "value": p.get(key)}
            for p in timeline
            if p.get("date") and isinstance(p.get(key), int | float)
        ]
        return pd.DataFrame(rows), f"Suchinteresse «{key}»"

    raise ValueError(f"unknown external kind: {kind}")


# ---------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------


def _compute_stats(merged: pd.DataFrame) -> dict[str, Any]:
    """Pearson + Spearman with p-values. Safe on small n."""
    n = len(merged)
    if n < 3:
        return {
            "n": n,
            "pearson_r": None,
            "pearson_p": None,
            "spearman_r": None,
            "spearman_p": None,
            "note": "too few aligned observations (need ≥ 3)",
        }
    a = merged["internal"].to_numpy(dtype=float)
    b = merged["external"].to_numpy(dtype=float)

    pearson = stats.pearsonr(a, b)
    spearman = stats.spearmanr(a, b)

    return {
        "n": n,
        "pearson_r": round(float(pearson.statistic), 4),
        "pearson_p": round(float(pearson.pvalue), 4),
        "spearman_r": round(float(spearman.statistic), 4),
        "spearman_p": round(float(spearman.pvalue), 4),
    }


def _align(internal: pd.DataFrame, external: pd.DataFrame) -> pd.DataFrame:
    """Inner-join on date. For weekly external series (Trends), match by
    the ISO week-start so the daily internal series gets aggregated to
    the same granularity."""
    if internal.empty or external.empty:
        return pd.DataFrame(columns=["date", "internal", "external"])

    ext_step = external["date"].sort_values().diff().median().days if len(external) > 1 else 1

    if ext_step >= 4:
        # External is weekly-ish. Aggregate internal up to weekly means
        # aligned on Mondays, then inner-merge.
        ai = (
            internal.set_index("date")["value"]
            .resample("W-MON", label="left", closed="left")
            .mean()
            .rename("internal")
            .reset_index()
        )
        ae = (
            external.set_index("date")["value"]
            .resample("W-MON", label="left", closed="left")
            .mean()
            .rename("external")
            .reset_index()
        )
        merged = ai.merge(ae, on="date", how="inner").dropna()
        return merged

    # Both daily-ish — simple inner merge.
    merged = (
        internal.rename(columns={"value": "internal"})
        .merge(external.rename(columns={"value": "external"}), on="date", how="inner")
        .dropna()
        .sort_values("date")
        .reset_index(drop=True)
    )
    return merged


# ---------------------------------------------------------------------
# Narrative via Claude
# ---------------------------------------------------------------------


_NARRATIVE_SYSTEM = """Sie erklären Manager:innen ohne Statistik-Hintergrund
das Ergebnis einer Korrelationsanalyse zwischen einer Shop-Kennzahl und
einer externen Zeitreihe.

REGELN:
- Maximal 3 Sätze. Lieber 2.
- Niemals «kausal», «verursacht», «getrieben durch» — Korrelation ist
  KEIN Kausalitätsnachweis. Verwenden Sie «bewegt sich gleichläufig
  mit», «zeigt einen Zusammenhang», «kein erkennbarer Zusammenhang».
- Nennen Sie konkret: r-Wert, p-Wert, n. Beispiel:
  «r = 0.12, p = 0.43, n = 12 Wochen — kein statistisch belastbarer
  Zusammenhang.»
- Bei n < 12 oder p > 0.10 ist die Aussage IMMER: kein belastbares
  Signal. Sagen Sie das explizit.
- Wenn Pearson und Spearman stark abweichen (|r_pearson - r_spearman|
  > 0.3), erwaehnen Sie das — es deutet auf einen monotonen aber nicht-
  linearen Zusammenhang.
- Am Ende: EIN konkreter Hinweis, was der/die Leser:in damit anfangen
  kann (z.B. «weiterhin beobachten», «nicht handlungsleitend»,
  «zusätzlich kausale Analyse aufsetzen»).
- Antwort als deutscher Fliesstext, ohne Aufzählungen, ohne Marker."""


def _narrate(
    *,
    internal_label: str,
    external_label: str,
    stats_summary: dict[str, Any],
    days: int,
) -> str | None:
    if not settings.anthropic_api_key:
        return None
    if stats_summary.get("pearson_r") is None:
        # Not enough data; skip the model call and just hand back a constant.
        return (
            f"Nur {stats_summary.get('n')} überlappende Datenpunkte — "
            f"kein belastbarer Zusammenhang ermittelbar."
        )

    client = Anthropic(api_key=settings.anthropic_api_key)
    payload = json.dumps(
        {
            "internal": internal_label,
            "external": external_label,
            "window_days": days,
            **stats_summary,
        },
        ensure_ascii=False,
        indent=2,
    )
    resp = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=400,
        system=_NARRATIVE_SYSTEM,
        messages=[{"role": "user", "content": payload}],
    )
    parts = [b.text for b in resp.content if b.type == "text"]
    return "\n".join(parts).strip() or None


# ---------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------


def correlate_with_shop(
    *,
    internal: str,
    external_kind: str,
    external_key: str,
    days: int = 90,
    today: date | None = None,
) -> dict[str, Any]:
    """Compute Pearson + Spearman between an internal Shop series and an
    external one, then ask Claude to interpret the result.

    Args:
        internal: which shop series — "shopify_revenue", "shopify_orders",
            "shopify_aov", or per-channel variants
            ("shopify_revenue_mobile", "shopify_orders_desktop", etc.).
        external_kind: "market" or "trends".
        external_key: yfinance symbol (e.g. "EURCHF=X") or Trends keyword.
        days: window in days (default 90).
        today: override for testing; defaults to date.today().

    Returns:
        {
            "internal":   {label, name, unit},
            "external":   {label, kind, key},
            "window_days": int,
            "stats":       {n, pearson_r, pearson_p, spearman_r, spearman_p},
            "series":      [{date, internal, external}, ...]  # for sparklines
            "narrative":   str | None,
        }
    """
    today = today or date.today()
    start = today - timedelta(days=days)

    spec = _resolve_internal(internal)
    internal_df = _fetch_internal(internal, start, today + timedelta(days=1))
    external_df, external_label = _fetch_external(external_kind, external_key, days)

    merged = _align(internal_df, external_df)
    stats_summary = _compute_stats(merged)

    narrative = _narrate(
        internal_label=spec["label"],
        external_label=external_label,
        stats_summary=stats_summary,
        days=days,
    )

    series = [
        {
            "date": row["date"].date().isoformat(),
            "internal": round(float(row["internal"]), 4),
            "external": round(float(row["external"]), 4),
        }
        for _, row in merged.iterrows()
    ]

    return {
        "internal": {"name": internal, "label": spec["label"], "unit": spec["unit"]},
        "external": {
            "kind": external_kind,
            "key": external_key,
            "label": external_label,
        },
        "window_days": days,
        "stats": stats_summary,
        "series": series,
        "narrative": narrative,
    }
