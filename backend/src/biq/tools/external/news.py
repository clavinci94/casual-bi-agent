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

# Region presets — each is a {source_name: rss_url} map.
#
# "default" is the legacy mix of DACH + global English business press,
# kept stable so existing callers don't get a surprise. "dach" is the
# tight CH/DE/AT business-press set the Markt-Radar uses for the
# national-market widget; sources are tagged with their country so the
# UI can group them. Easy to add "global" or "us" presets later.
_RSS_PRESETS: dict[str, dict[str, str]] = {
    "default": {
        "Tagesanzeiger Wirtschaft": "https://www.tagesanzeiger.ch/wirtschaft.rss",
        "NZZ Wirtschaft": "https://www.nzz.ch/wirtschaft.rss",
        "Reuters Business": "https://feeds.reuters.com/reuters/businessNews",
        "Handelsblatt": "https://www.handelsblatt.com/contentexport/feed/schlagzeilen",
        "Spiegel Wirtschaft": "https://www.spiegel.de/wirtschaft/index.rss",
    },
    # DACH set — eight verified-working public RSS endpoints across CH/DE/AT.
    # Handelszeitung (CH) and Wirtschaftswoche (DE) were on the wish-list but
    # both publishers have killed their public RSS feeds; their content is
    # paywalled. We substitute the strongest available alternatives so the
    # NewsAPI domain list (below) can still cover them when a paid key is
    # configured.
    "dach": {
        "NZZ Wirtschaft (CH)": "https://www.nzz.ch/wirtschaft.rss",
        "SRF Wirtschaft (CH)": "https://www.srf.ch/news/bnf/rss/1646",
        "Handelsblatt (DE)": "https://www.handelsblatt.com/contentexport/feed/schlagzeilen",
        "Manager Magazin (DE)": "https://www.manager-magazin.de/index.rss",
        "FAZ Wirtschaft (DE)": "https://www.faz.net/rss/aktuell/wirtschaft/",
        "Süddeutsche Wirtschaft (DE)": "https://rss.sueddeutsche.de/rss/wirtschaft",
        "Der Standard Wirtschaft (AT)": "https://www.derstandard.at/rss/wirtschaft",
        "ORF Wirtschaft (AT)": "https://rss.orf.at/news.xml",
    },
}

# NewsAPI counterpart of the DACH preset — restrict to publisher domains
# so the paid path can also reach paywalled sources whose public RSS is
# disabled (Handelszeitung, Wirtschaftswoche). NewsAPI indexes their
# article URLs even when their feeds are dead.
_DACH_NEWSAPI_DOMAINS = ",".join(
    [
        "handelszeitung.ch",
        "nzz.ch",
        "srf.ch",
        "wiwo.de",
        "handelsblatt.com",
        "manager-magazin.de",
        "faz.net",
        "sueddeutsche.de",
        "derstandard.at",
        "orf.at",
    ]
)


def news_search(
    query: str = "",
    *,
    max_results: int = 10,
    language: str = "de",
    region: str = "default",
) -> dict[str, Any]:
    """Return recent news matching `query`.

    Args:
        query: free-text filter (e.g. "Shopify mobile checkout"). Empty
            string returns top recent headlines.
        max_results: 1..30
        language: ISO code passed to NewsAPI; ignored by the RSS fallback.
        region: which source preset to use. "default" (current legacy mix)
            or "dach" (CH/DE/AT business press only). Unknown values fall
            back to "default".

    Returns dict shape:
        {
            "query": str,
            "region": str,
            "provider": "newsapi" | "rss",
            "results": [{title, source, published_at, url, summary}],
            "cache": "hit" | "miss",
        }
    """
    cap = max(1, min(int(max_results), 30))
    preset = region if region in _RSS_PRESETS else "default"
    cache_key = f"news::{language}::{preset}::n={cap}::{query.strip()}"

    def fetch() -> dict[str, Any]:
        if settings.newsapi_key:
            return _fetch_newsapi(query, cap, language, preset)
        return _fetch_rss(query, cap, preset)

    return cached_query(
        source="news",
        query_key=cache_key,
        ttl_minutes=_DEFAULT_TTL_MINUTES,
        fetch=fetch,
    )


def _fetch_newsapi(query: str, max_results: int, language: str, region: str) -> dict[str, Any]:
    try:
        params: dict[str, Any] = {
            "apiKey": settings.newsapi_key,
            "language": language,
            "pageSize": max_results,
            "sortBy": "publishedAt",
        }
        # `domains` only applies to /everything, not /top-headlines.
        use_everything = bool(query) or region == "dach"
        if use_everything:
            url = "https://newsapi.org/v2/everything"
            if query:
                params["q"] = query
            if region == "dach":
                params["domains"] = _DACH_NEWSAPI_DOMAINS
        else:
            url = "https://newsapi.org/v2/top-headlines"
            params["country"] = "de" if language == "de" else "us"

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
        return {
            "query": query,
            "region": region,
            "provider": "newsapi",
            "results": results,
        }
    except Exception as exc:
        _logger.warning("newsapi fetch failed: %s — falling back to RSS", exc)
        return _fetch_rss(query, max_results, region)


def _fetch_rss(query: str, max_results: int, region: str = "default") -> dict[str, Any]:
    feeds = _RSS_PRESETS.get(region) or _RSS_PRESETS["default"]
    try:
        import feedparser

        entries: list[dict[str, Any]] = []
        q = query.lower().strip()
        for source_name, feed_url in feeds.items():
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
            "region": region,
            "provider": "rss",
            "results": entries[:max_results],
        }
    except Exception as exc:
        _logger.warning("rss fetch failed: %s", exc)
        return {
            "error": f"rss fetch failed: {exc}",
            "query": query,
            "region": region,
            "results": [],
        }


def _now() -> str:
    return datetime.now(UTC).isoformat()
