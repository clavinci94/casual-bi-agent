"""Shopify Admin API connector + ETL.

Pulls orders / customers / products from a Shopify store and upserts
them into `raw.shopify_*`. Designed for a single store (the
SHOPIFY_SHOP_DOMAIN env var); multi-tenant comes later if needed.

Pattern:
    from biq.tools import shopify
    shopify.sync_all()                        # runs orders + customers + products
    shopify.sync_orders(since_iso="2024-01")  # incremental

Auth: a Custom App's Admin API access token (`shpat_...`). See
docs/shopify-setup.md for the setup walkthrough.

REST API is used (not GraphQL) — simpler for the volumes a typical
dev-store demo produces (≪ 10k entities total). Pagination follows
the Link-header `rel="next"` cursor pattern. We never raise on
upstream rate-limits (429): we sleep + retry inside the loop.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import text

from biq.config import settings
from biq.db import engine

_logger = logging.getLogger(__name__)


class ShopifyNotConfiguredError(RuntimeError):
    """Raised when shop domain or token isn't set in .env."""


def _base_url() -> str:
    if not settings.shopify_shop_domain or not settings.shopify_admin_api_token:
        raise ShopifyNotConfiguredError(
            "SHOPIFY_SHOP_DOMAIN and SHOPIFY_ADMIN_API_TOKEN must both be set."
        )
    return f"https://{settings.shopify_shop_domain}/admin/api/{settings.shopify_api_version}"


def _headers() -> dict[str, str]:
    return {
        "X-Shopify-Access-Token": settings.shopify_admin_api_token or "",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _paginate(
    path: str,
    params: dict[str, Any] | None = None,
    page_size: int = 250,
) -> Iterator[dict[str, Any]]:
    """Yield every record from a paginated Shopify REST endpoint.

    Shopify's pagination uses Link headers with `rel="next"` cursors.
    We follow them until the header is gone. Built-in retry on 429.
    """
    url = f"{_base_url()}{path}"
    query: dict[str, Any] = {"limit": page_size, **(params or {})}

    with httpx.Client(timeout=30.0, headers=_headers()) as client:
        while True:
            for _attempt in range(5):
                resp = client.get(url, params=query)
                if resp.status_code == 429:
                    wait = float(resp.headers.get("Retry-After", "2"))
                    _logger.warning("shopify rate-limited, sleeping %ss", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                break
            else:
                raise RuntimeError("shopify rate-limit retries exhausted")

            yield resp.json()

            # Follow Link rel="next" pagination
            link = resp.headers.get("Link") or resp.headers.get("link") or ""
            match = re.search(r'<([^>]+)>;\s*rel="next"', link)
            if not match:
                break
            url = match.group(1)
            # After the first page Shopify wants the cursor in the URL,
            # not duplicated as query params.
            query = {}


def _to_decimal(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


# ---- Orders -----------------------------------------------------------


def sync_orders(since_iso: str | None = None) -> dict[str, Any]:
    """Pull orders newer than `since_iso` (or all if None) and upsert.

    Returns a summary dict: {entity, rows_upserted, error?, since_iso}.
    """
    params: dict[str, Any] = {"status": "any"}
    if since_iso:
        params["updated_at_min"] = since_iso

    inserted = 0
    sync_id = _begin_sync("orders", since_iso)
    try:
        for page in _paginate("/orders.json", params=params):
            for o in page.get("orders", []):
                _upsert_order(o)
                inserted += 1
        _finish_sync(sync_id, inserted)
    except Exception as exc:
        _finish_sync(sync_id, inserted, error=str(exc)[:500])
        raise
    return {"entity": "orders", "rows_upserted": inserted, "since_iso": since_iso}


def _upsert_order(order: dict[str, Any]) -> None:
    customer = order.get("customer") or {}
    line_items = order.get("line_items") or []
    payload = {
        "order_id": str(order["id"]),
        "order_number": str(order.get("order_number") or order.get("name") or ""),
        "created_at": _to_dt(order.get("created_at")),
        "updated_at": _to_dt(order.get("updated_at")),
        "processed_at": _to_dt(order.get("processed_at")),
        "cancelled_at": _to_dt(order.get("cancelled_at")),
        "customer_id": str(customer.get("id")) if customer.get("id") else None,
        "email": order.get("email"),
        "financial_status": order.get("financial_status"),
        "fulfillment_status": order.get("fulfillment_status"),
        "total_price": _to_decimal(order.get("total_price")),
        "subtotal_price": _to_decimal(order.get("subtotal_price")),
        "total_discounts": _to_decimal(order.get("total_discounts")),
        "total_shipping": _to_decimal(
            (order.get("total_shipping_price_set") or {})
            .get("shop_money", {})
            .get("amount")
        ),
        "total_tax": _to_decimal(order.get("total_tax")),
        "currency": order.get("currency"),
        "line_items_count": len(line_items),
        "source_name": order.get("source_name"),
        "raw": json.dumps(order, default=str),
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO raw.shopify_orders
                    (order_id, order_number, created_at, updated_at, processed_at,
                     cancelled_at, customer_id, email, financial_status,
                     fulfillment_status, total_price, subtotal_price,
                     total_discounts, total_shipping, total_tax, currency,
                     line_items_count, source_name, raw)
                VALUES
                    (:order_id, :order_number, :created_at, :updated_at,
                     :processed_at, :cancelled_at, :customer_id, :email,
                     :financial_status, :fulfillment_status, :total_price,
                     :subtotal_price, :total_discounts, :total_shipping,
                     :total_tax, :currency, :line_items_count, :source_name,
                     cast(:raw as jsonb))
                ON CONFLICT (order_id) DO UPDATE SET
                    updated_at = EXCLUDED.updated_at,
                    cancelled_at = EXCLUDED.cancelled_at,
                    financial_status = EXCLUDED.financial_status,
                    fulfillment_status = EXCLUDED.fulfillment_status,
                    total_price = EXCLUDED.total_price,
                    raw = EXCLUDED.raw,
                    synced_at = now()
                """
            ),
            payload,
        )


# ---- Customers --------------------------------------------------------


def sync_customers(since_iso: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if since_iso:
        params["updated_at_min"] = since_iso

    inserted = 0
    sync_id = _begin_sync("customers", since_iso)
    try:
        for page in _paginate("/customers.json", params=params):
            for c in page.get("customers", []):
                _upsert_customer(c)
                inserted += 1
        _finish_sync(sync_id, inserted)
    except Exception as exc:
        _finish_sync(sync_id, inserted, error=str(exc)[:500])
        raise
    return {"entity": "customers", "rows_upserted": inserted, "since_iso": since_iso}


def _upsert_customer(c: dict[str, Any]) -> None:
    addr = c.get("default_address") or {}
    payload = {
        "customer_id": str(c["id"]),
        "email": c.get("email"),
        "created_at": _to_dt(c.get("created_at")),
        "updated_at": _to_dt(c.get("updated_at")),
        "orders_count": c.get("orders_count"),
        "total_spent": _to_decimal(c.get("total_spent")),
        "state": c.get("state"),
        "accepts_marketing": c.get("accepts_marketing"),
        "default_address_country": addr.get("country_code"),
        "default_address_province": addr.get("province_code"),
        "raw": json.dumps(c, default=str),
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO raw.shopify_customers
                    (customer_id, email, created_at, updated_at, orders_count,
                     total_spent, state, accepts_marketing,
                     default_address_country, default_address_province, raw)
                VALUES
                    (:customer_id, :email, :created_at, :updated_at, :orders_count,
                     :total_spent, :state, :accepts_marketing,
                     :default_address_country, :default_address_province,
                     cast(:raw as jsonb))
                ON CONFLICT (customer_id) DO UPDATE SET
                    email = EXCLUDED.email,
                    orders_count = EXCLUDED.orders_count,
                    total_spent = EXCLUDED.total_spent,
                    state = EXCLUDED.state,
                    accepts_marketing = EXCLUDED.accepts_marketing,
                    raw = EXCLUDED.raw,
                    synced_at = now()
                """
            ),
            payload,
        )


# ---- Products ---------------------------------------------------------


def sync_products(since_iso: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if since_iso:
        params["updated_at_min"] = since_iso

    inserted = 0
    sync_id = _begin_sync("products", since_iso)
    try:
        for page in _paginate("/products.json", params=params):
            for p in page.get("products", []):
                _upsert_product(p)
                inserted += 1
        _finish_sync(sync_id, inserted)
    except Exception as exc:
        _finish_sync(sync_id, inserted, error=str(exc)[:500])
        raise
    return {"entity": "products", "rows_upserted": inserted, "since_iso": since_iso}


def _upsert_product(p: dict[str, Any]) -> None:
    payload = {
        "product_id": str(p["id"]),
        "title": p.get("title"),
        "handle": p.get("handle"),
        "vendor": p.get("vendor"),
        "product_type": p.get("product_type"),
        "created_at": _to_dt(p.get("created_at")),
        "updated_at": _to_dt(p.get("updated_at")),
        "published_at": _to_dt(p.get("published_at")),
        "status": p.get("status"),
        "raw": json.dumps(p, default=str),
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO raw.shopify_products
                    (product_id, title, handle, vendor, product_type,
                     created_at, updated_at, published_at, status, raw)
                VALUES
                    (:product_id, :title, :handle, :vendor, :product_type,
                     :created_at, :updated_at, :published_at, :status,
                     cast(:raw as jsonb))
                ON CONFLICT (product_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    status = EXCLUDED.status,
                    updated_at = EXCLUDED.updated_at,
                    raw = EXCLUDED.raw,
                    synced_at = now()
                """
            ),
            payload,
        )


# ---- Orchestration ----------------------------------------------------


def sync_all(since_iso: str | None = None) -> list[dict[str, Any]]:
    """Run all three syncs sequentially. Returns a list of per-entity
    summaries. Errors in one entity don't block the others."""
    summaries: list[dict[str, Any]] = []
    for fn, name in [
        (sync_products, "products"),
        (sync_customers, "customers"),
        (sync_orders, "orders"),
    ]:
        try:
            summaries.append(fn(since_iso=since_iso))
        except Exception as exc:
            _logger.exception("sync %s failed", name)
            summaries.append({"entity": name, "error": str(exc)})
    return summaries


def last_successful_sync(entity: str) -> datetime | None:
    """The most recent successful sync timestamp for an entity, or None
    if there has been no successful run yet. Use this to pick the
    `updated_at_min` for an incremental sync."""
    sql = text(
        "SELECT MAX(finished_at) FROM raw.shopify_sync_log "
        "WHERE entity = :entity AND error IS NULL AND finished_at IS NOT NULL"
    )
    with engine.connect() as conn:
        result = conn.execute(sql, {"entity": entity}).scalar_one_or_none()
    return result if isinstance(result, datetime) else None


# ---- Sync-log bookkeeping --------------------------------------------


def _begin_sync(entity: str, since_iso: str | None) -> str:
    """Insert a sync_log row and return its id."""
    import uuid as _uuid

    sync_id = str(_uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO raw.shopify_sync_log (sync_id, entity, since_iso) "
                "VALUES (:id, :entity, :since)"
            ),
            {"id": sync_id, "entity": entity, "since": since_iso},
        )
    return sync_id


def _finish_sync(sync_id: str, rows: int, error: str | None = None) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE raw.shopify_sync_log "
                "SET finished_at = now(), rows_upserted = :rows, error = :err "
                "WHERE sync_id = :id"
            ),
            {"id": sync_id, "rows": rows, "err": error},
        )


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


# -------- aggregates for the Markt-Radar / briefing widgets ----------


def top_product_categories(
    *,
    limit: int = 5,
    window_days: int = 90,
    min_revenue: float = 0.0,
) -> dict[str, Any]:
    """Return the top revenue-generating product_types in the last N days.

    The Markt-Radar's Trends widget needs realistic default keywords to
    show search-interest data for. Empty defaults ("sneaker, adidas")
    are generic — these are shop-specific.

    Joins `raw.shopify_orders.raw->'line_items'` (JSONB array) against
    `raw.shopify_products.product_id`, sums quantity * price per
    product_type, returns the top N.

    Args:
        limit: top-N categories to return (default 5, the Markt-Radar uses 3-5).
        window_days: revenue window in days (default 90).
        min_revenue: floor — a category with revenue below this is omitted
            entirely, so an almost-empty shop doesn't surface a tail noise
            category as a "top" pick.

    Returns:
        {
            "window_days": int,
            "categories": [
                {"product_type": str, "revenue": float, "units_sold": int,
                 "n_orders": int},
                ...
            ],
            "horizon": {"start": iso, "end": iso}  // empty if no orders
        }

    The function is safe on an empty shop (returns categories=[]).
    """
    sql = text(
        """
        WITH expanded AS (
            SELECT
                o.order_id,
                (li->>'product_id')             AS product_id,
                COALESCE((li->>'quantity')::int, 0)    AS quantity,
                COALESCE((li->>'price')::numeric, 0)   AS unit_price
            FROM raw.shopify_orders o,
                 LATERAL jsonb_array_elements(
                     COALESCE(o.raw->'line_items', '[]'::jsonb)
                 ) li
            WHERE o.created_at >= now() - make_interval(days => :win)
              AND o.cancelled_at IS NULL
        )
        SELECT
            p.product_type,
            SUM(e.quantity * e.unit_price)::float8 AS revenue,
            SUM(e.quantity)::int                   AS units_sold,
            COUNT(DISTINCT e.order_id)             AS n_orders
        FROM expanded e
        JOIN raw.shopify_products p ON p.product_id = e.product_id
        WHERE p.product_type IS NOT NULL AND p.product_type <> ''
        GROUP BY p.product_type
        HAVING SUM(e.quantity * e.unit_price) >= :min_rev
        ORDER BY revenue DESC
        LIMIT :lim
        """
    )

    horizon_sql = text(
        "SELECT MIN(created_at), MAX(created_at) FROM raw.shopify_orders "
        "WHERE created_at >= now() - make_interval(days => :win) "
        "  AND cancelled_at IS NULL"
    )

    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {"win": window_days, "min_rev": float(min_revenue), "lim": int(limit)},
        ).all()
        horizon = conn.execute(horizon_sql, {"win": window_days}).first()

    categories = [
        {
            "product_type": r[0],
            "revenue": round(float(r[1]), 2),
            "units_sold": int(r[2]),
            "n_orders": int(r[3]),
        }
        for r in rows
    ]

    return {
        "window_days": window_days,
        "categories": categories,
        "horizon": {
            "start": horizon[0].isoformat() if horizon and horizon[0] else None,
            "end": horizon[1].isoformat() if horizon and horizon[1] else None,
        },
    }


def top_category_keywords(*, limit: int = 5, window_days: int = 90) -> list[str]:
    """Convenience wrapper: just the lowercased product_type strings.

    The Trends widget wants a flat string list as its default keywords;
    this hides the schema of `top_product_categories` from the frontend
    caller.
    """
    payload = top_product_categories(limit=limit, window_days=window_days)
    return [c["product_type"].lower() for c in payload["categories"]]
