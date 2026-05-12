"""News headlines aggregation.

Two-tier strategy:
1. If NEWSAPI_KEY is set, use newsapi.org's `/v2/everything` endpoint —
   structured headlines with publishedAt, source, description.
2. Otherwise fall back to a curated set of public RSS feeds (Tagesanzeiger,
   NZZ Wirtschaft, Reuters Business, Handelsblatt, Bloomberg). RSS is
   free, no key needed, and good enough for the Markt-Radar page.

The agent's investigator should reach for this when an anomaly might be
externally caused (a competitor news event, a sector-wide shock, etc.).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from biq.config import settings
from biq.tools.external.cache import cached_query

_logger = logging.getLogger(__name__)

_DEFAULT_TTL_MINUTES = 30

# RSS fallback — German-language business + general news, in priority order.
_RSS_FEEDS: dict[str, str] = {
    "Tagesanzeiger Wirtschaft": "https://www.tagesanzeiger.ch/wirtschaft.rss",
    "NZZ Wirtschaft": "https://www.nzz.ch/wirtschaft.rss",
    "Reuters Business": "https://feeds.reuters.com/reuters/businessNews",
    "Handelsblatt": "https://www.handelsblatt.com/contentexport/feed/schlagzeilen",
    "Spiegel Wirtschaft": "https://www.spiegel.de/wirtschaft/index.rss",
}


def news_search(
    query: str = "",
    *,
    max_results: int = 10,
    language: str = "de",
) -> dict[str, Any]:
    """Return recent news matching `query`.

    Args:
        query: free-text filter (e.g. "Shopify mobile checkout"). Empty
            string returns top recent headlines.
        max_results: 1..30
        language: ISO code passed to NewsAPI; ignored by the RSS fallback.

    Returns dict shape:
        {
            "query": str,
            "provider": "newsapi" | "rss",
            "results": [{title, source, published_at, url, summary}],
            "cache": "hit" | "miss",
        }
    """
    cap = max(1, min(int(max_results), 30))
    cache_key = f"news::{language}::n={cap}::{query.strip()}"

    def fetch() -> dict[str, Any]:
        if settings.newsapi_key:
            return _fetch_newsapi(query, cap, language)
        return _fetch_rss(query, cap)

    return cached_query(
        source="news",
        query_key=cache_key,
        ttl_minutes=_DEFAULT_TTL_MINUTES,
        fetch=fetch,
    )


def _fetch_newsapi(query: str, max_results: int, language: str) -> dict[str, Any]:
    try:
        params: dict[str, Any] = {
            "apiKey": settings.newsapi_key,
            "language": language,
            "pageSize": max_results,
            "sortBy": "publishedAt",
        }
        if query:
            params["q"] = query
            url = "https://newsapi.org/v2/everything"
        else:
            params["country"] = "de" if language == "de" else "us"
            url = "https://newsapi.org/v2/top-headlines"

        with httpx.Client(timeout=15.0) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            data = r.json()

        results = [
            {
                "title": a.get("title"),
                "source": (a.get("source") or {}).get("name"),
                "published_at": a.get("publishedAt"),
                "url": a.get("url"),
                "summary": a.get("description"),
            }
            for a in data.get("articles", [])
        ]
        return {"query": query, "provider": "newsapi", "results": results}
    except Exception as exc:
        _logger.warning("newsapi fetch failed: %s — falling back to RSS", exc)
        return _fetch_rss(query, max_results)


def _fetch_rss(query: str, max_results: int) -> dict[str, Any]:
    try:
        import feedparser

        entries: list[dict[str, Any]] = []
        q = query.lower().strip()
        for source_name, feed_url in _RSS_FEEDS.items():
            try:
                parsed = feedparser.parse(feed_url)
            except Exception:
                continue
            for e in parsed.entries[:25]:
                title = e.get("title") or ""
                summary = (e.get("summary") or "")[:400]
                if q and q not in title.lower() and q not in summary.lower():
                    continue
                published = e.get("published") or e.get("updated") or ""
                # Normalise to ISO when possible
                try:
                    from email.utils import parsedate_to_datetime

                    published_iso = parsedate_to_datetime(published).astimezone(UTC).isoformat()
                except Exception:
                    published_iso = published
                entries.append(
                    {
                        "title": title,
                        "source": source_name,
                        "published_at": published_iso,
                        "url": e.get("link"),
                        "summary": summary,
                    }
                )

        # Sort newest first, truncate.
        entries.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        return {
            "query": query,
            "provider": "rss",
            "results": entries[:max_results],
        }
    except Exception as exc:
        _logger.warning("rss fetch failed: %s", exc)
        return {"error": f"rss fetch failed: {exc}", "query": query, "results": []}


def _now() -> str:
    return datetime.now(UTC).isoformat()
