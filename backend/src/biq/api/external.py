"""External intelligence routes — power the /markt-radar page.

Thin wrappers around biq.tools.external. Caching happens in the tool
layer (shared with the investigator's audit-logged calls), so two users
loading the page within the cache TTL share one upstream API hit.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from biq.tools.correlation import correlate_with_shop
from biq.tools.external import (
    commerce_calendar,
    market_snapshot,
    news_search,
    shopify_status,
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
    region: Annotated[str, Query(pattern="^(default|dach)$")] = "default",
) -> dict[str, Any]:
    """Recent news (NewsAPI if key present, else RSS aggregator).

    `region="dach"` restricts the source list to verified CH/DE/AT
    business-press feeds.
    """
    return news_search(q, max_results=max_results, language=language, region=region)


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


@router.get("/shopify-status")
def shopify_status_route() -> dict[str, Any]:
    """Live Shopify platform status from status.shopify.com.

    Cached 5 minutes upstream — repeated hits within that window do not
    re-query Shopify.
    """
    return shopify_status()


@router.get("/commerce-calendar")
def commerce_calendar_route(
    country: Annotated[str, Query(pattern="^(CH|DE|AT)$")] = "CH",
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
    window_days: Annotated[int, Query(ge=30, le=365)] = 270,
) -> dict[str, Any]:
    """Upcoming commerce dates: statutory holidays + BFCM / Singles' Day /
    Mother's & Father's Day / Christmas / etc., for one DACH country."""
    return commerce_calendar(country=country, limit=limit, window_days=window_days)


@router.get("/correlate-with-shop")
def correlate_with_shop_route(
    internal: Annotated[str, Query(min_length=1, max_length=64)],
    external_kind: Annotated[str, Query(pattern="^(market|trends)$")],
    external_key: Annotated[str, Query(min_length=1, max_length=64)],
    days: Annotated[int, Query(ge=14, le=365)] = 90,
) -> dict[str, Any]:
    """Pearson + Spearman correlation between an internal Shop series
    (e.g. `shopify_revenue`) and an external one (market symbol or
    Trends keyword), with a Claude-generated 2-3-sentence interpretation.
    """
    return correlate_with_shop(
        internal=internal,
        external_kind=external_kind,
        external_key=external_key,
        days=days,
    )
