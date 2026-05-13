"""Shop-level Shopify aggregates that aren't classical KPI views.

The KPI views (kpi.shopify_*) hand back daily series. This router is
for richer derived facts that the Markt-Radar / briefing widgets need —
currently just the revenue-weighted top product categories.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query

from biq.tools import shopify as shopify_tools

router = APIRouter(prefix="/shopify", tags=["shopify"])


@router.get("/top-categories")
def top_categories(
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    window_days: Annotated[int, Query(ge=7, le=730)] = 90,
    min_revenue: Annotated[float, Query(ge=0.0)] = 0.0,
) -> dict[str, Any]:
    """Top-N revenue-generating product types in the last N days.

    Used by the Trends widget to default to the shop's own categories
    instead of a generic placeholder list.
    """
    return shopify_tools.top_product_categories(
        limit=limit, window_days=window_days, min_revenue=min_revenue
    )
