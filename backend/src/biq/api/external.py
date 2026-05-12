"""External intelligence routes — power the /markt-radar page.

Thin wrappers around biq.tools.external. Caching happens in the tool
layer (shared with the investigator's audit-logged calls), so two users
loading the page within the cache TTL share one upstream API hit.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from biq.tools.external import (
    market_snapshot,
    news_search,
    trends_query,
    web_search,
)

router = APIRouter(prefix="/external", tags=["external"])


@router.get("/search")
def search(
    q: Annotated[str, Query(min_length=1, max_length=400)],
    max_results: Annotated[int, Query(ge=1, le=10)] = 5,
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
    topic: Annotated[str, Query(pattern="^(general|news)$")] = "general",
) -> dict[str, Any]:
    """Web search via Tavily."""
    return web_search(q, max_results=max_results, days=days, topic=topic)


@router.get("/news")
def news(
    q: Annotated[str, Query(max_length=200)] = "",
    max_results: Annotated[int, Query(ge=1, le=30)] = 10,
    language: Annotated[str, Query(pattern="^(de|en)$")] = "de",
) -> dict[str, Any]:
    """Recent news (NewsAPI if key present, else RSS aggregator)."""
    return news_search(q, max_results=max_results, language=language)


@router.get("/trends")
def trends(
    keywords: Annotated[list[str], Query(min_length=1, max_length=5)],
    geo: Annotated[str, Query(max_length=4)] = "CH",
    timeframe: Annotated[str, Query(max_length=40)] = "today 3-m",
) -> dict[str, Any]:
    """Google-Trends interest-over-time for 1..5 keywords."""
    return trends_query(keywords, geo=geo, timeframe=timeframe)


@router.get("/market")
def market(
    symbols: Annotated[list[str] | None, Query()] = None,
    period: Annotated[str, Query(pattern="^(5d|1mo|3mo|6mo|1y)$")] = "1mo",
) -> dict[str, Any]:
    """Equity / index / FX / commodity snapshot from Yahoo Finance."""
    return market_snapshot(symbols, period=period)
