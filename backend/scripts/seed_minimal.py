"""Minimal self-contained seed for CI / quick local bootstrap.

Creates a small synthetic dataset that exercises the same code paths
as the full Olist + simulator pipeline. Includes the deliberately-
injected mobile_checkout_v2 regression so all golden tests pass.

Volume (deterministic from SIMULATION_SEED):
    raw.customers    ~500
    raw.sellers      10
    raw.products     50
    raw.orders       2000   (spread Feb 2018..May 2018)
    raw.order_items  2000
    raw.payments     2000
    raw.releases     6
    raw.campaigns    50
    raw.web_events   ~25k
    raw.support_tickets 100

Usage:
    DATABASE_URL=... uv run python scripts/seed_minimal.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from biq.config import settings
from biq.seeders.synthetic import (
    gen_campaigns,
    gen_releases,
    gen_support_tickets,
    gen_web_events,
    truncate_targets,
    write,
)

N_CUSTOMERS = 1000
N_SELLERS = 10
N_PRODUCTS = 50
N_ORDERS = 5000


def _seed_core(rng: np.random.Generator) -> None:
    sellers = pd.DataFrame(
        {
            "seller_id": [f"seller_{i:03d}" for i in range(N_SELLERS)],
            "seller_zip_prefix": [f"{rng.integers(10000, 99999)}" for _ in range(N_SELLERS)],
            "seller_city": "city",
            "seller_state": rng.choice(["SP", "RJ", "MG", "RS", "BA"], N_SELLERS),
        }
    )
    write(sellers, "raw", "sellers")

    customers = pd.DataFrame(
        {
            "customer_id": [f"cust_{i:04d}" for i in range(N_CUSTOMERS)],
            "customer_unique_id": [f"unique_{i:04d}" for i in range(N_CUSTOMERS)],
            "customer_zip_prefix": [f"{rng.integers(10000, 99999)}" for _ in range(N_CUSTOMERS)],
            "customer_city": "city",
            "customer_state": rng.choice(["SP", "RJ", "MG", "RS", "BA"], N_CUSTOMERS),
        }
    )
    write(customers, "raw", "customers")

    products = pd.DataFrame(
        {
            "product_id": [f"prod_{i:03d}" for i in range(N_PRODUCTS)],
            "category": rng.choice(["electronics", "books", "fashion", "food"], N_PRODUCTS),
            "weight_g": rng.integers(100, 5000, N_PRODUCTS),
        }
    )
    write(products, "raw", "products")

    start = pd.Timestamp("2018-02-01", tz="UTC")
    end = pd.Timestamp("2018-05-31", tz="UTC")
    total_seconds = int((end - start).total_seconds())
    offsets = rng.integers(0, total_seconds, N_ORDERS)
    purchase_ts = start + pd.to_timedelta(offsets, unit="s")
    delivered_ts = purchase_ts + pd.Timedelta(days=7)

    customer_ids = rng.choice(customers["customer_id"], N_ORDERS)
    orders = pd.DataFrame(
        {
            "order_id": [f"ord_{i:05d}" for i in range(N_ORDERS)],
            "customer_id": customer_ids,
            "order_status": rng.choice(
                ["delivered", "delivered", "delivered", "canceled"], N_ORDERS
            ),
            "purchase_ts": purchase_ts,
            "delivered_customer_ts": delivered_ts,
        }
    )
    write(orders, "raw", "orders")

    prices = rng.integers(50, 500, N_ORDERS).astype(float)
    freight = rng.integers(10, 50, N_ORDERS).astype(float)
    items = pd.DataFrame(
        {
            "order_id": orders["order_id"],
            "item_seq": 1,
            "product_id": rng.choice(products["product_id"], N_ORDERS),
            "seller_id": rng.choice(sellers["seller_id"], N_ORDERS),
            "price": prices,
            "freight": freight,
        }
    )
    write(items, "raw", "order_items")

    payments = pd.DataFrame(
        {
            "order_id": orders["order_id"],
            "payment_seq": 1,
            "payment_type": "credit_card",
            "installments": 1,
            "value": prices + freight,
        }
    )
    write(payments, "raw", "payments")


def main() -> None:
    print(f"SIMULATION_SEED = {settings.simulation_seed}")
    rng = np.random.default_rng(settings.simulation_seed)

    print("\nTruncating raw.*")
    truncate_targets(
        [
            ("raw", "reviews"),
            ("raw", "payments"),
            ("raw", "order_items"),
            ("raw", "orders"),
            ("raw", "products"),
            ("raw", "sellers"),
            ("raw", "customers"),
            ("raw", "web_events"),
            ("raw", "campaigns"),
            ("raw", "releases"),
            ("raw", "support_tickets"),
        ]
    )

    print("\nCore entities (customers / sellers / products / orders / items / payments):")
    _seed_core(rng)

    print("\nReleases:")
    write(gen_releases(), "raw", "releases")

    print("\nCampaigns:")
    write(gen_campaigns(rng), "raw", "campaigns")

    print("\nWeb events:")
    write(gen_web_events(rng, scale=1.0), "raw", "web_events")

    print("\nSupport tickets:")
    write(gen_support_tickets(rng, n=100), "raw", "support_tickets")

    print("\nDone.")


if __name__ == "__main__":
    main()
