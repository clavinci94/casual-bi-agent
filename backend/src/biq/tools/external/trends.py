"""Google Trends via pytrends.

Unofficial library — Google could change the endpoint at any time.
We wrap it defensively: every request is short-cached so we hit Google
at most a few times per hour, and any failure falls back to an empty
result so the agent loop keeps running.
"""

from __future__ import annotations

import logging
from typing import Any

from biq.tools.external.cache import cached_query

_logger = logging.getLogger(__name__)

_DEFAULT_TTL_MINUTES = 90


def trends_query(
    keywords: list[str],
    *,
    geo: str = "CH",
    timeframe: str = "today 3-m",
) -> dict[str, Any]:
    """Search-interest timeline for one or more keywords.

    Args:
        keywords: 1..5 search terms. Google compares them relative to each
            other, so "shoes" alone == 100; "shoes" vs "boots" is relative.
        geo: ISO country code. "CH" = Switzerland, "DE" = Germany,
            "" (empty) = worldwide.
        timeframe: pytrends-compatible spec:
            "now 7-d" / "today 3-m" / "today 12-m" / "2018-01-01 2018-12-31"

    Returns:
        {
            "keywords": [...],
            "geo": str,
            "timeframe": str,
            "timeline": [{date, <kw>: value, ...}],
            "related_topics": [str, ...],
            "cache": "hit" | "miss",
        }
        or {"error": ..., "timeline": []}
    """
    if not keywords:
        return {"error": "at least one keyword required", "timeline": []}

    kw_list = [k.strip() for k in keywords if k.strip()][:5]
    cache_key = f"trends::geo={geo}::tf={timeframe}::kw={','.join(kw_list)}"

    return cached_query(
        source="trends",
        query_key=cache_key,
        ttl_minutes=_DEFAULT_TTL_MINUTES,
        fetch=lambda: _fetch(kw_list, geo, timeframe),
    )


def _fetch(keywords: list[str], geo: str, timeframe: str) -> dict[str, Any]:
    try:
        # pytrends pulls in pandas; lazy-import to keep cold-start fast.
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="de-CH", tz=120, timeout=(10, 30))
        pytrends.build_payload(keywords, geo=geo, timeframe=timeframe)
        df = pytrends.interest_over_time()
        if df is None or df.empty:
            return {
                "keywords": keywords,
                "geo": geo,
                "timeframe": timeframe,
                "timeline": [],
                "related_topics": [],
            }

        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        timeline = [
            {"date": idx.strftime("%Y-%m-%d"), **{k: int(row[k]) for k in keywords if k in row}}
            for idx, row in df.iterrows()
        ]

        related: list[str] = []
        try:
            rt = pytrends.related_topics()
            for k in keywords:
                bucket = (rt.get(k) or {}).get("top")
                if bucket is None:
                    continue
                related.extend(bucket.head(5)["topic_title"].tolist())
        except Exception:
            # Related-topics is best-effort; Google often 429s here.
            pass

        return {
            "keywords": keywords,
            "geo": geo,
            "timeframe": timeframe,
            "timeline": timeline,
            "related_topics": list(dict.fromkeys(related))[:10],
        }
    except Exception as exc:
        _logger.warning("trends fetch failed: %s", exc)
        return {
            "error": f"google trends call failed: {exc}",
            "keywords": keywords,
            "timeline": [],
        }
