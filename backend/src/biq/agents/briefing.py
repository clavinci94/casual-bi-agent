"""Tagesbriefing — the morning-paper for a Swiss Shopify Plus merchant.

Gathers eight external + internal signal blocks, hands them to Claude
with strict "be skeptical, quote verbatim, 3-5 signals max" rules, and
persists the structured result.

Unlike the investigator, this is NOT a multi-step tool loop. It's a
single synthesis call — the agent does not get tools to call, it gets
all the data in the prompt. Why:

- Briefing data is bounded (today's market + last 14 days KPIs + news);
  a tool loop would burn iterations without gaining new evidence.
- Single call = predictable cost (~CHF 0.10) and predictable latency
  (~10 s), which matters because this runs on a daily cron.
- Structured output via `tool_use` (`submit_briefing`) forces the
  expected schema and prevents free-form drift.

Every signal fetch is still audit-logged so a reviewer can replay the
inputs that produced a given briefing.

Cache strategy: one briefing per calendar day. A second call on the
same day returns the cached one unless `force_refresh=True`. Cron jobs
should ALWAYS pass `force_refresh=True`; user-facing reads should not.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from anthropic import Anthropic
from sqlalchemy import text

from biq.audit import finish_step, log_step, log_tool_call, run_context
from biq.config import settings
from biq.db import engine
from biq.tools import shopify as shopify_tools
from biq.tools.external import (
    commerce_calendar,
    market_snapshot,
    news_search,
    shopify_status,
    trends_query,
)

_logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"

# Symbols a Swiss Shopify-Plus shop should care about — local indices
# plus the FX crosses that move their cross-border margins.
_DACH_SYMBOLS = [
    "^SSMI",  # SMI (Switzerland)
    "^GDAXI",  # DAX (Germany)
    "^ATX",  # ATX (Austria)
    "EURCHF=X",  # cost of selling into the EUR zone from CH
    "USDCHF=X",  # USD-denominated suppliers / Shopify billing
    "CHFEUR=X",  # CH-buyer-facing prices in EUR shops
]


SYSTEM_PROMPT = """Sie sind der "Tagesbriefing"-Analyst für einen Schweizer
Shopify-Plus-Online-Shop. Jeden Morgen schreiben Sie ein extrem knappes
Briefing: was draussen heute geschehen ist, das diesen einen Shop
konkret angeht.

REGELN — ohne Ausnahme:
1. Maximal FÜNF Signale. Ein Signal ist "konkret" wenn es eine
   nachvollziehbare Konsequenz für Umsatz, Marge, Versand, Marketing,
   Conversion oder Kundenerfahrung dieses Shops hat. Reine Makro-
   Nachrichten ohne erkennbare Wirkung sind KEIN Signal.
2. Jede zitierte Zahl muss WÖRTLICH aus den vorliegenden Daten kommen.
   Keine Schätzungen, keine Rundungen "über den Daumen", keine
   "ungefähr so wie letztes Jahr"-Aussagen.
3. Lieber WENIGER Signale als zu viele. Wenn die Daten heute ruhig
   sind, geben Sie 0-2 Signale aus mit headline "Heute ruhig, internes
   Geschäft stabil" — das ist eine gültige Antwort.
4. Jedes Signal hat drei Teile (über das `submit_briefing` Tool):
   - what: was ist passiert? (1 kurzer Satz, mit der zitierten Zahl)
   - why_for_you: warum für diesen Shop relevant? (1 Satz, max. 25 Wörter)
   - action: was tun? (konkret, messbar, mit Frist)
5. Vermeiden Sie technischen Jargon. Manager lesen das. Beispiel:
   "Conversion-Rate" ist ok, "rel_effect_lower_95ci" nicht.
6. Eskalation (urgency=high) nur wenn Handlung innerhalb 24-48h
   tatsächlich nötig ist (z.B. Shopify-Outage betrifft uns aktuell,
   Apple-Pay-Brücke wieder aktiv). Sonst medium oder low.

Sie GEBEN dieses Briefing AUS via dem Tool `submit_briefing`. Eine
freie Antwort ohne Tool-Call zählt nicht."""


SUBMIT_TOOL = {
    "name": "submit_briefing",
    "description": "Submit the structured daily briefing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {
                "type": "string",
                "description": "Eine Zeile, die die Tageslage zusammenfasst.",
            },
            "signals": {
                "type": "array",
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "what": {"type": "string"},
                        "why_for_you": {"type": "string"},
                        "action": {"type": "string"},
                        "urgency": {"type": "string", "enum": ["low", "medium", "high"]},
                        "source": {
                            "type": "string",
                            "description": "Welcher Datenblock liefert das Signal — z.B. 'markets', 'news', 'shopify_status', 'commerce_calendar', 'trends', 'kpis'.",
                        },
                    },
                    "required": ["what", "why_for_you", "action", "urgency", "source"],
                },
            },
        },
        "required": ["headline", "signals"],
    },
}


# ---------------------------------------------------------------------
# Signal collection
# ---------------------------------------------------------------------


def _shopify_kpi_snapshot(days: int = 14) -> dict[str, Any]:
    """Read last-N-days Shopify KPIs from the governed views."""
    sql = text(
        """
        SELECT day, channel, orders_completed, revenue, aov
        FROM kpi.shopify_orders_daily
        WHERE day >= current_date - make_interval(days => :days)
        ORDER BY day, channel
        """
    )
    summary_sql = text(
        """
        WITH win AS (
            SELECT day, channel, orders_completed, revenue
            FROM kpi.shopify_orders_daily
            WHERE day >= current_date - make_interval(days => :days)
        )
        SELECT
            channel,
            SUM(orders_completed)::int AS orders,
            SUM(revenue)::float8        AS revenue,
            COUNT(DISTINCT day)         AS days
        FROM win
        GROUP BY channel
        ORDER BY revenue DESC
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(sql, {"days": days}).all()
        per_channel = conn.execute(summary_sql, {"days": days}).all()

    daily = [
        {
            "day": r[0].isoformat(),
            "channel": r[1],
            "orders": int(r[2] or 0),
            "revenue": round(float(r[3] or 0.0), 2),
            "aov": round(float(r[4] or 0.0), 2),
        }
        for r in rows
    ]
    summary = [
        {
            "channel": r[0],
            "orders_total": int(r[1] or 0),
            "revenue_total": round(float(r[2] or 0.0), 2),
            "days_with_data": int(r[3] or 0),
        }
        for r in per_channel
    ]

    return {"window_days": days, "by_channel": summary, "daily": daily}


def _gather_signals(ctx: Any) -> dict[str, Any]:
    """Call all six signal fetchers, audit each, return one bundled dict.

    A failure on any single signal must NOT abort the briefing — it just
    becomes an empty section. The LLM will mention "X data unavailable"
    when relevant.
    """
    signals: dict[str, Any] = {}

    fetchers: list[tuple[str, str, Any]] = [
        ("markets", "market_snapshot", lambda: market_snapshot(symbols=_DACH_SYMBOLS, period="5d")),
        ("shopify_status", "shopify_status", lambda: shopify_status()),
        (
            "commerce_calendar",
            "commerce_calendar",
            lambda: commerce_calendar(country="CH", limit=6),
        ),
        ("news", "news_search", lambda: news_search(max_results=12, region="dach")),
        (
            "top_categories",
            "shopify.top_product_categories",
            lambda: shopify_tools.top_product_categories(limit=5, window_days=90),
        ),
        ("kpis", "kpi.shopify_orders_daily", lambda: _shopify_kpi_snapshot(days=14)),
    ]

    for key, tool_name, fetch in fetchers:
        step_id = log_step(ctx, "briefing", f"fetch::{key}")
        try:
            payload = fetch()
            signals[key] = payload
            log_tool_call(
                step_id,
                tool_name,
                params={"key": key},
                result_summary=_signal_size(payload),
                rows=_signal_rows(payload),
            )
            finish_step(step_id, output={"key": key, "ok": True})
        except Exception as exc:
            _logger.warning("briefing signal '%s' failed: %s", key, exc)
            signals[key] = {"error": str(exc)}
            log_tool_call(step_id, tool_name, params={"key": key}, error=str(exc))
            finish_step(step_id, output={"key": key, "ok": False, "error": str(exc)})

    # The Trends fetch depends on top_categories, so it's last.
    keywords = [
        c["product_type"].lower()
        for c in (signals.get("top_categories", {}).get("categories") or [])
    ][:5]
    step_id = log_step(ctx, "briefing", "fetch::trends", input={"keywords": keywords})
    try:
        trends = (
            trends_query(keywords=keywords, geo="CH", timeframe="today 3-m")
            if keywords
            else {"timeline": [], "keywords": [], "note": "no top categories"}
        )
        signals["trends"] = trends
        log_tool_call(
            step_id,
            "trends_query",
            params={"keywords": keywords, "geo": "CH"},
            result_summary={"n_points": len(trends.get("timeline") or [])},
        )
        finish_step(step_id, output={"keywords": keywords, "ok": True})
    except Exception as exc:
        signals["trends"] = {"error": str(exc)}
        log_tool_call(step_id, "trends_query", params={"keywords": keywords}, error=str(exc))
        finish_step(step_id, output={"ok": False, "error": str(exc)})

    return signals


def _signal_size(payload: Any) -> dict[str, Any]:
    """Small summary the audit table can store cheaply."""
    if isinstance(payload, dict):
        return {"keys": list(payload.keys())[:10], "type": "dict"}
    if isinstance(payload, list):
        return {"len": len(payload), "type": "list"}
    return {"type": type(payload).__name__}


def _signal_rows(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    for k in ("results", "events", "items", "categories", "daily", "components"):
        v = payload.get(k)
        if isinstance(v, list):
            return len(v)
    return 0


def _compact_signals_for_prompt(signals: dict[str, Any]) -> dict[str, Any]:
    """Strip unbounded fields before sending to Claude so we don't burn
    20k tokens on news snippets the synthesis doesn't need.
    """
    compact: dict[str, Any] = {}

    m = signals.get("markets") or {}
    compact["markets"] = {
        "period": m.get("period"),
        "items": [
            {
                "symbol": it.get("symbol"),
                "name": it.get("name"),
                "last": it.get("last"),
                "change_pct": it.get("change_pct"),
            }
            for it in (m.get("items") or [])
        ],
    }

    s = signals.get("shopify_status") or {}
    compact["shopify_status"] = {
        "overall": s.get("overall"),
        "active_incidents": [
            {
                "name": i.get("name"),
                "impact": i.get("impact"),
                "status": i.get("status"),
                "components": i.get("components"),
                "started_at": i.get("started_at"),
            }
            for i in (s.get("active_incidents") or [])
        ],
        "critical_components_not_operational": [
            {"name": c.get("name"), "status": c.get("status")}
            for c in (s.get("components") or [])
            if c.get("is_critical") and c.get("status") != "operational"
        ],
    }

    c = signals.get("commerce_calendar") or {}
    compact["commerce_calendar"] = {
        "today": c.get("today"),
        "events": [
            {
                "name": e.get("name"),
                "date": e.get("date"),
                "days_away": e.get("days_away"),
                "kind": e.get("kind"),
                "note": e.get("note"),
            }
            for e in (c.get("events") or [])
        ],
    }

    n = signals.get("news") or {}
    compact["news"] = {
        "provider": n.get("provider"),
        "results": [
            {
                "title": r.get("title"),
                "source": r.get("source"),
                "published_at": r.get("published_at"),
            }
            for r in (n.get("results") or [])[:12]
        ],
    }

    t = signals.get("trends") or {}
    timeline = t.get("timeline") or []
    per_keyword: dict[str, dict[str, Any]] = {}
    for kw in t.get("keywords") or []:
        values = [p.get(kw) for p in timeline if isinstance(p.get(kw), int | float)]
        if values:
            per_keyword[kw] = {
                "min": min(values),
                "max": max(values),
                "last": values[-1],
                "n_points": len(values),
            }
    compact["trends"] = {
        "keywords": t.get("keywords"),
        "per_keyword": per_keyword,
    }

    tc = signals.get("top_categories") or {}
    compact["top_categories"] = {
        "window_days": tc.get("window_days"),
        "categories": tc.get("categories") or [],
    }

    k = signals.get("kpis") or {}
    compact["kpis"] = {
        "window_days": k.get("window_days"),
        "by_channel": k.get("by_channel"),
        # Daily series — only keep the last 7 days to keep prompt size sane;
        # the channel rollup above is enough for trend-level reasoning.
        "last_7_days": (k.get("daily") or [])[-28:],  # 7 days x 4 channels
    }

    return compact


# ---------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------


_BRIEFING_OUTPUT_SQL = text(
    """
    SELECT r.run_id, r.finished_at, s.output
    FROM audit.agent_runs r
    JOIN audit.agent_steps s ON s.run_id = r.run_id
    WHERE r.trigger = 'briefing'
      AND r.status = 'ok'
      AND s.action = 'synthesize'
      AND r.finished_at::date = current_date
    ORDER BY r.finished_at DESC
    LIMIT 1
    """
)


def get_today_briefing() -> dict[str, Any] | None:
    """Return today's cached briefing if one exists, else None."""
    with engine.connect() as conn:
        row = conn.execute(_BRIEFING_OUTPUT_SQL).first()
    if row is None:
        return None
    run_id, finished_at, output = row[0], row[1], row[2]
    if not isinstance(output, dict):
        return None
    return {
        "run_id": run_id,
        "generated_at": finished_at.isoformat() if finished_at else None,
        "briefing": output.get("briefing"),
        "from_cache": True,
    }


# ---------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------


def validate_briefing_shape(briefing: dict[str, Any]) -> list[str]:
    """Return a list of structural defects in a briefing dict; empty list
    means well-formed. Used by smoke tests and the eval suite to gate
    further (paid) checks behind a cheap structural one.
    """
    defects: list[str] = []
    signals = briefing.get("signals")
    if not isinstance(signals, list):
        return ["briefing.signals is not a list"]
    if len(signals) == 0:
        defects.append("briefing has zero signals")
    if len(signals) > 5:
        defects.append(f"briefing has {len(signals)} signals; max is 5")
    for i, s in enumerate(signals):
        if not isinstance(s, dict):
            defects.append(f"signals[{i}] is not an object")
            continue
        for field in ("what", "why_for_you", "action", "urgency", "source"):
            v = s.get(field)
            if not isinstance(v, str) or not v.strip():
                defects.append(f"signals[{i}].{field} missing or empty")
        if s.get("urgency") not in {"low", "medium", "high"}:
            defects.append(f"signals[{i}].urgency = {s.get('urgency')!r}")
    if not briefing.get("headline"):
        defects.append("briefing.headline missing")
    return defects


def generate_briefing(
    *,
    force_refresh: bool = False,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 2048,
) -> dict[str, Any]:
    """Generate (or return today's cached) Tagesbriefing.

    Args:
        force_refresh: when True, ignore today's cache and always call
            the model. Cron workflows should use True; user-facing reads
            should leave it False.
        model: anthropic model id.
        max_tokens: cap on Claude's response; briefing output is short.

    Returns dict shape:
        {
            "run_id": str,
            "generated_at": iso,
            "briefing": {headline, signals: [...]},
            "from_cache": bool,
        }

    Raises:
        RuntimeError when ANTHROPIC_API_KEY is missing.
    """
    if not force_refresh:
        cached = get_today_briefing()
        if cached is not None:
            return cached

    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set. Add it to .env to run the briefing.")

    client = Anthropic(api_key=settings.anthropic_api_key)

    with run_context(trigger="briefing", prompt="Tagesbriefing für CH Shopify-Plus-Shop") as ctx:
        signals = _gather_signals(ctx)
        compact = _compact_signals_for_prompt(signals)

        user_payload = json.dumps(
            {
                "today": date.today().isoformat(),
                "shop_context": "Schweizer Shopify-Plus-Shop",
                "signals": compact,
            },
            default=str,
            indent=2,
            ensure_ascii=False,
        )

        # Persist the compact signal bundle on the synthesize step so the
        # eval judge can verify the briefing's claims against the EXACT
        # data the agent saw, not against fresh re-fetched values.
        step_id = log_step(
            ctx,
            "briefing",
            "synthesize",
            input={"model": model, "compact_signals": compact},
        )

        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[
                {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
            ],
            tools=[SUBMIT_TOOL],
            tool_choice={"type": "tool", "name": "submit_briefing"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Hier sind die Daten für heute. Folgen Sie den Regeln "
                        "im System-Prompt strikt. Geben Sie das Briefing "
                        "ausschliesslich via `submit_briefing` aus.\n\n" + user_payload
                    ),
                }
            ],
        )

        briefing: dict[str, Any] | None = None
        for block in resp.content:
            if block.type == "tool_use" and block.name == "submit_briefing":
                briefing = dict(block.input)
                break

        if briefing is None:
            error_msg = f"agent did not call submit_briefing (stop_reason={resp.stop_reason})"
            finish_step(step_id, output={"error": error_msg})
            raise RuntimeError(error_msg)

        finish_step(step_id, output={"briefing": briefing})

        return {
            "run_id": ctx.run_id,
            "generated_at": None,
            "briefing": briefing,
            "from_cache": False,
        }
