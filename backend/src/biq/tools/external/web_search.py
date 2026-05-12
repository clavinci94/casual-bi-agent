"""Tavily-backed web search.

Tavily is a search API optimised for LLM consumption — it returns
short, scored result snippets with title + url + content excerpt.
Free tier covers 1000 queries/month, more than enough for the agent +
Markt-Radar combined while we're below ~30 active sessions/day.
"""

from __future__ import annotations

import logging
from typing import Any

from biq.config import settings
from biq.tools.external.cache import cached_query

_logger = logging.getLogger(__name__)

_DEFAULT_TTL_MINUTES = 60  # web facts change hour-by-hour; cache aggressively short


def web_search(
    query: str,
    *,
    max_results: int = 5,
    days: int | None = None,
    topic: str = "general",
) -> dict[str, Any]:
    """Search the public web via Tavily.

    Args:
        query: natural-language query.
        max_results: how many results to return (1..10).
        days: limit to last N days for time-sensitive queries.
        topic: 'general' or 'news' — Tavily ranks the corpus differently.

    Returns:
        {
            "query": str,
            "answer": str,                   # short synthesised answer if Tavily gives one
            "results": [{title, url, content, score, published_date?}],
            "cache": "hit" | "miss",
        }
        or {"error": ..., "results": []}
    """
    if not settings.tavily_api_key:
        return {
            "error": "TAVILY_API_KEY not configured on the backend.",
            "query": query,
            "results": [],
        }

    cap = max(1, min(int(max_results), 10))
    cache_key = f"web::{topic}::days={days}::n={cap}::{query.strip()}"

    return cached_query(
        source="tavily",
        query_key=cache_key,
        ttl_minutes=_DEFAULT_TTL_MINUTES,
        fetch=lambda: _fetch(query, cap, days, topic),
    )


def _fetch(query: str, max_results: int, days: int | None, topic: str) -> dict[str, Any]:
    try:
        # Lazy import — only at call time so a missing key doesn't break module import.
        from tavily import TavilyClient

        client = TavilyClient(api_key=settings.tavily_api_key)
        kwargs: dict[str, Any] = {
            "query": query,
            "search_depth": "basic",
            "max_results": max_results,
            "topic": topic,
        }
        if days is not None:
            kwargs["days"] = max(1, int(days))

        resp = client.search(**kwargs)
        results = [
            {
                "title": r.get("title"),
                "url": r.get("url"),
                "content": r.get("content"),
                "score": r.get("score"),
                "published_date": r.get("published_date"),
            }
            for r in resp.get("results", [])
        ]
        return {
            "query": query,
            "answer": resp.get("answer"),
            "results": results,
        }
    except Exception as exc:
        _logger.warning("tavily fetch failed: %s", exc)
        return {"error": f"tavily call failed: {exc}", "query": query, "results": []}
