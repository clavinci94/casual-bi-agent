"""Manual / cron entry point for the Shopify ETL.

Usage:
    # Full sync from scratch
    uv run python scripts/shopify_sync.py

    # Incremental (only changes since the last successful run per entity)
    uv run python scripts/shopify_sync.py --incremental

    # Explicit since_iso
    uv run python scripts/shopify_sync.py --since 2024-01-01

    # Single entity
    uv run python scripts/shopify_sync.py --entity orders
"""

from __future__ import annotations

import argparse
import json

from biq.config import settings
from biq.tools import shopify


def main() -> None:
    parser = argparse.ArgumentParser(description="Shopify → raw.shopify_* ETL")
    parser.add_argument(
        "--entity",
        choices=["orders", "customers", "products", "all"],
        default="all",
    )
    parser.add_argument("--since", help="ISO datetime (inclusive). Overrides --incremental.")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Use last successful sync per entity as since.",
    )
    args = parser.parse_args()

    if not settings.shopify_shop_domain or not settings.shopify_admin_api_token:
        raise SystemExit(
            "SHOPIFY_SHOP_DOMAIN and SHOPIFY_ADMIN_API_TOKEN must be set in .env. "
            "See docs/shopify-setup.md."
        )

    def _since_for(entity: str) -> str | None:
        if args.since:
            return args.since
        if args.incremental:
            last = shopify.last_successful_sync(entity)
            return last.isoformat() if last else None
        return None

    if args.entity == "all":
        summaries: list[dict] = []
        for fn, name in [
            (shopify.sync_products, "products"),
            (shopify.sync_customers, "customers"),
            (shopify.sync_orders, "orders"),
        ]:
            try:
                summaries.append(fn(since_iso=_since_for(name)))
            except Exception as exc:
                summaries.append({"entity": name, "error": str(exc)})
        print(json.dumps(summaries, indent=2, default=str))
    else:
        fn = {
            "orders": shopify.sync_orders,
            "customers": shopify.sync_customers,
            "products": shopify.sync_products,
        }[args.entity]
        result = fn(since_iso=_since_for(args.entity))
        print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
