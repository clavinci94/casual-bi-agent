"""Shopify platform status — direct from status.shopify.com.

Shopify's status page is the authoritative source for outages affecting
every Shopify merchant: Admin, Checkout, Payments, API, Email, etc.
A live incident there is often the explanation for an anomaly in a
specific merchant's data — the Apple-Pay-iOS-26 case from May 2026 is
the canonical example.

We hit the public statuspage.io API (no key required):

    https://status.shopify.com/api/v2/summary.json

The response shape comes from statuspage.io and is stable in practice.
We narrow it to the fields a merchant operator cares about:

    {
        "overall": {"indicator": "none|minor|major|critical", "description": "..."},
        "components": [
            {"name": "Checkout", "status": "operational", "is_critical": true}
        ],
        "active_incidents": [
            {
                "name": "Apple Pay outage",
                "impact": "major",
                "status": "monitoring",
                "started_at": "2026-05-12T14:00:00Z",
                "components": ["Checkout", "Payments"],
                "url": "https://status.shopify.com/incidents/xyz"
            }
        ],
        "scheduled_maintenances": [...]
    }

Cached 5 minutes — a status flip during an outage matters within minutes,
but we don't need to hammer the upstream.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from biq.tools.external.cache import cached_query

_logger = logging.getLogger(__name__)

_SUMMARY_URL = "https://www.shopifystatus.com/api/v2/summary.json"
_TIMEOUT_S = 10.0
_DEFAULT_TTL_MINUTES = 5

# Components a merchant operator typically cares about most. Used to mark
# rows in the UI with extra prominence — the full list of all components
# is still returned.
_CRITICAL_COMPONENT_NAMES = {
    "checkout",
    "online store",
    "storefront",
    "admin",
    "payments",
    "shopify payments",
    "shopify email",
    "api & apps",
    "api",
    "mobile apps",
    "point of sale",
    "pos",
}


def _is_critical(name: str | None) -> bool:
    if not name:
        return False
    return name.strip().lower() in _CRITICAL_COMPONENT_NAMES


def _component_summary(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": c.get("name"),
        "status": c.get("status"),  # operational | degraded_performance | partial_outage | major_outage | under_maintenance
        "is_critical": _is_critical(c.get("name")),
        "updated_at": c.get("updated_at"),
    }


def _incident_summary(inc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": inc.get("id"),
        "name": inc.get("name"),
        "impact": inc.get("impact"),  # none | minor | major | critical
        "status": inc.get("status"),  # investigating | identified | monitoring | resolved
        "started_at": inc.get("started_at") or inc.get("created_at"),
        "updated_at": inc.get("updated_at"),
        "components": [
            c.get("name") for c in (inc.get("components") or []) if c.get("name")
        ],
        "url": inc.get("shortlink") or inc.get("incident_url"),
    }


def _fetch_status() -> dict[str, Any]:
    try:
        # follow_redirects=True so a domain move like
        # status.shopify.com → www.shopifystatus.com (May 2026) doesn't
        # silently break us when Shopify changes hosts again.
        with httpx.Client(timeout=_TIMEOUT_S, follow_redirects=True) as client:
            resp = client.get(
                _SUMMARY_URL,
                headers={"Accept": "application/json", "User-Agent": "causal-bi/0.1"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        _logger.warning("shopify status fetch failed: %s", exc)
        return {"error": f"shopify status fetch failed: {exc}", "active_incidents": []}

    status = data.get("status") or {}
    # statuspage.io returns both individual components and "group" folders
    # that hold sub-components. Merchants want services, not folders.
    components = [
        _component_summary(c)
        for c in (data.get("components") or [])
        if not c.get("group") and c.get("name")
    ]

    incidents = [_incident_summary(i) for i in (data.get("incidents") or [])]
    maintenances = [
        _incident_summary(m) for m in (data.get("scheduled_maintenances") or [])
    ]

    return {
        "overall": {
            "indicator": status.get("indicator", "none"),
            "description": status.get("description", "All Systems Operational"),
        },
        "components": components,
        "active_incidents": incidents,
        "scheduled_maintenances": maintenances,
        "fetched_from": _SUMMARY_URL,
    }


def shopify_status(*, ttl_minutes: int = _DEFAULT_TTL_MINUTES) -> dict[str, Any]:
    """Return Shopify's current platform status.

    Cached for `ttl_minutes` — a flapping outage indicator is not useful,
    but missing a real one for too long is. 5 minutes is the sweet spot
    Shopify's own statuspage refreshes at.
    """
    return cached_query(
        source="shopify_status",
        query_key="summary",
        ttl_minutes=ttl_minutes,
        fetch=_fetch_status,
    )
