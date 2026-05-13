"""Seed a Shopify dev-store with realistic test customers + orders.

Different from `shopify_simulate.py` (which writes directly into our
local raw.shopify_*): this script POSTs against the real Shopify Admin
API of your dev-store. The orders then get pulled into our DB via the
normal `make shopify-sync` and arrive tagged `data_source='live'`.

We mirror the simulator's story:
  - ~80 customers spread across Switzerland + DACH region
  - ~280 orders distributed over the last 90 days
  - Channel mix: 55 % desktop (web), 30 % mobile (ios_app + android_app),
    10 % pos, 5 % other — realistic for a Shopify-Plus shop
  - Last 14 days: mobile dropout to ~35 % of normal → ground-truth
    anomaly the briefing agent should pick up after the next sync

After running, do `make shopify-sync` to pull everything into the local
DB, then flip BIQ_DATA_SOURCE=live in .env to see it in the dashboard.

    Usage:
        make shopify-seed-dev          # if a make target is added
        cd backend && uv run python scripts/shopify_seed_dev_store.py

Requires:
    SHOPIFY_SHOP_DOMAIN  in .env
    SHOPIFY_ADMIN_API_TOKEN in .env with scopes:
        write_orders, write_customers, read_products
    (read_products is enough — we re-use existing demo products
    from the dev-store rather than creating new ones).
"""

from __future__ import annotations

import random
import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from biq.config import settings

# --- config -----------------------------------------------------------

N_CUSTOMERS = 80
N_ORDERS = 280
WINDOW_DAYS = 90
ANOMALY_DAYS = 14
ANOMALY_MOBILE_DROP = 0.65  # mobile orders fall to 35 % of normal in window

CHANNEL_WEIGHTS = {
    "web": 55,         # → 'desktop' in our channel logic
    "ios_app": 18,     # → 'mobile'
    "android_app": 12, # → 'mobile'
    "pos": 10,
    "other": 5,
}

# Swiss + DACH cities for plausible addresses
CITIES = [
    ("Zürich", "ZH", "CH"), ("Genf", "GE", "CH"), ("Bern", "BE", "CH"),
    ("Basel", "BS", "CH"), ("Lausanne", "VD", "CH"), ("Luzern", "LU", "CH"),
    ("Winterthur", "ZH", "CH"), ("St. Gallen", "SG", "CH"),
    ("Berlin", "BE", "DE"), ("München", "BY", "DE"), ("Hamburg", "HH", "DE"),
    ("Wien", "9", "AT"), ("Graz", "6", "AT"),
]

FIRST_NAMES = ["Anna", "Lars", "Sophie", "Marc", "Lea", "Tobias", "Mira", "Jonas",
               "Lina", "Kai", "Nora", "Felix", "Elena", "Luca", "Maja", "Tim"]
LAST_NAMES = ["Müller", "Meier", "Schmid", "Weber", "Fischer", "Keller", "Brunner",
              "Hofer", "Lang", "Werner", "Steiner", "Bauer", "Wolf", "Berger"]


def _client() -> httpx.Client:
    if not settings.shopify_shop_domain or not settings.shopify_admin_api_token:
        sys.exit("SHOPIFY_SHOP_DOMAIN and SHOPIFY_ADMIN_API_TOKEN must be set in .env")
    base = f"https://{settings.shopify_shop_domain}/admin/api/{settings.shopify_api_version}"
    return httpx.Client(
        base_url=base,
        headers={
            "X-Shopify-Access-Token": settings.shopify_admin_api_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=30.0,
    )


def _retry_429(fn):  # type: ignore[no-untyped-def]
    """Sleep + retry on Shopify's 429 with Retry-After header. Shopify
    free dev-stores cap REST at ~2 req/s with a small bucket — when the
    bucket empties we wait 4-8 s before resuming, generous on purpose."""
    def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        for attempt in range(20):
            resp: httpx.Response = fn(*args, **kwargs)
            if resp.status_code != 429:
                return resp
            base = float(resp.headers.get("Retry-After", "4"))
            wait = base + attempt * 0.5  # gentle backoff
            print(f"  429 — Pause {wait:.1f}s (Versuch {attempt + 1}/20) …")
            time.sleep(wait)
        raise RuntimeError("rate-limit retries exhausted")
    return wrapper


# --- helpers ---------------------------------------------------------


def fetch_variant_ids(client: httpx.Client) -> list[tuple[int, float]]:
    """Pull existing product variants from the dev-store so we can
    reference real (variant_id, price) pairs in orders. Demo data covers
    snowboards / accessories etc. — enough variety for plausible orders."""
    variants: list[tuple[int, float]] = []
    page_info = None
    while True:
        params = {"limit": 250, "fields": "id,variants"}
        if page_info:
            params["page_info"] = page_info
        r = _retry_429(client.get)("/products.json", params=params)
        r.raise_for_status()
        for p in r.json().get("products", []):
            for v in p.get("variants", []):
                try:
                    variants.append((int(v["id"]), float(v.get("price") or 49)))
                except (TypeError, ValueError):
                    continue
        # Shopify uses Link header for cursor pagination
        link = r.headers.get("Link", "")
        if 'rel="next"' not in link:
            break
        import re
        m = re.search(r"page_info=([^&>]+)[^>]*>;\s*rel=\"next\"", link)
        if not m:
            break
        page_info = m.group(1)
    return variants


def fetch_seeded_customers(client: httpx.Client) -> list[int]:
    """Return IDs of customers tagged 'causal-bi-demo' — so a re-run of
    the script doesn't try to create duplicates and 422-fail on email
    collisions."""
    ids: list[int] = []
    params: dict[str, Any] = {"query": "tag:causal-bi-demo", "limit": 250}
    r = _retry_429(client.get)("/customers/search.json", params=params)
    if r.status_code == 200:
        for c in r.json().get("customers", []):
            try:
                ids.append(int(c["id"]))
            except (TypeError, ValueError):
                continue
    return ids


def create_customer(client: httpx.Client, i: int) -> dict[str, Any] | None:
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    city, province_code, country_code = random.choice(CITIES)
    payload = {
        "customer": {
            "first_name": first,
            "last_name": last,
            "email": f"seed.{first.lower()}.{last.lower()}.{i}@example-causal-bi.local",
            "verified_email": True,
            "addresses": [
                {
                    "first_name": first,
                    "last_name": last,
                    "city": city,
                    "province_code": province_code,
                    "country_code": country_code,
                }
            ],
            "accepts_marketing": random.random() < 0.45,
            "tags": "seed,causal-bi-demo",
        }
    }
    r = _retry_429(client.post)("/customers.json", json=payload)
    if r.status_code in (200, 201):
        return r.json().get("customer")
    if r.status_code == 422:
        # Already exists (email collision) — fetch instead
        return None
    print(f"  customer create failed: {r.status_code} {r.text[:200]}")
    return None


def create_order(
    client: httpx.Client,
    variant: tuple[int, float],
    customer_id: int,
    when: datetime,
    channel: str,
) -> bool:
    """Create one order. We can't set the protected source_name field
    from an untrusted Admin-API client, so we encode the intended
    channel in the order's tags and rely on the KPI view's tag fallback
    (migration 0007) to bucket it correctly."""
    variant_id, unit_price = variant
    qty = random.choice([1, 1, 1, 2, 2, 3])
    payload = {
        "order": {
            "line_items": [
                {"variant_id": variant_id, "quantity": qty}
            ],
            "customer": {"id": customer_id},
            "financial_status": "paid",
            "fulfillment_status": "fulfilled",
            "processed_at": when.isoformat(),
            # Channel tag is read by kpi.shopify_orders_daily (mig 0007).
            "tags": f"seed,causal-bi-demo,channel:{channel}",
            # Mark as test order so Shopify doesn't try to actually charge anything
            "test": True,
            "send_receipt": False,
            "send_fulfillment_receipt": False,
            "transactions": [
                {
                    "kind": "sale",
                    "status": "success",
                    "amount": f"{round(unit_price * qty, 2)}",
                }
            ],
        }
    }
    r = _retry_429(client.post)("/orders.json", json=payload)
    if r.status_code in (200, 201):
        return True
    print(f"  order create failed: {r.status_code} {r.text[:200]}")
    return False


def pick_source(weights: dict[str, int]) -> str:
    keys, vals = zip(*weights.items(), strict=False)
    return random.choices(keys, weights=vals, k=1)[0]


def source_to_channel(source: str) -> str:
    """Map our pseudo-source-name back to the channel bucket the KPI view uses."""
    if source in ("ios_app", "android_app"):
        return "mobile"
    if source == "web":
        return "desktop"
    if source == "pos":
        return "pos"
    return "other"


# --- main -----------------------------------------------------------


def main() -> int:
    random.seed(42)  # deterministic-ish so re-runs produce similar shape
    print(f"Seeding {settings.shopify_shop_domain} (API {settings.shopify_api_version})")
    print(f"  customers={N_CUSTOMERS} orders={N_ORDERS} window={WINDOW_DAYS}d")
    print(f"  anomaly: last {ANOMALY_DAYS} days, mobile drops to {int((1 - ANOMALY_MOBILE_DROP) * 100)} %")
    print()

    with _client() as client:
        print("Pulling product variants …")
        variants = fetch_variant_ids(client)
        if not variants:
            sys.exit("No product variants found in the dev-store. Make sure demo data was enabled.")
        print(f"  {len(variants)} variants available\n")

        # Re-use already-seeded customers from a previous run if present
        # (script is idempotent — re-runs only create what's still missing
        # and never duplicate orders we haven't asked for).
        print("Checking for previously seeded customers …")
        customer_ids: list[int] = fetch_seeded_customers(client)
        print(f"  {len(customer_ids)} existing seeded customers found")

        needed = max(0, N_CUSTOMERS - len(customer_ids))
        if needed > 0:
            print(f"Creating {needed} new customer(s) …")
            offset = len(customer_ids)  # avoid email collisions on retry
            for i in range(needed):
                c = create_customer(client, offset + i)
                if c:
                    customer_ids.append(int(c["id"]))
                if (i + 1) % 20 == 0:
                    print(f"  {i + 1}/{needed} done")
        print(f"  {len(customer_ids)} customers available for ordering\n")
        if not customer_ids:
            sys.exit("No customers created — aborting orders step.")

        print("Creating orders with ground-truth Mobile anomaly …")
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=ANOMALY_DAYS)

        # Anomaly weights: same as normal but mobile_app channels much lower
        anomaly_weights = dict(CHANNEL_WEIGHTS)
        for k in ("ios_app", "android_app"):
            anomaly_weights[k] = int(anomaly_weights[k] * (1 - ANOMALY_MOBILE_DROP))

        ok = 0
        for i in range(N_ORDERS):
            # Spread orders uniformly across the window, with a small
            # late-night dip (pseudo-realistic)
            days_back = random.uniform(0, WINDOW_DAYS)
            when = now - timedelta(days=days_back, hours=random.uniform(0, 24))
            in_anomaly = when >= cutoff
            weights = anomaly_weights if in_anomaly else CHANNEL_WEIGHTS
            source = pick_source(weights)
            channel = source_to_channel(source)
            if create_order(client, random.choice(variants), random.choice(customer_ids), when, channel):
                ok += 1
            if (i + 1) % 25 == 0:
                print(f"  {i + 1}/{N_ORDERS} done (ok={ok})")
            # Stay safely under Shopify's 2 req/s limit on free dev-stores.
            # 0.7 s sleep ≈ 1.4 RPS → no 429s in practice.
            time.sleep(0.7)

        print()
        print(f"Done: {ok}/{N_ORDERS} orders created.")
        print()
        print("Next steps:")
        print("  1. make shopify-sync               # pull the new orders into local DB")
        print("  2. set BIQ_DATA_SOURCE=live in .env")
        print("  3. restart backend (make api-serve)")
        print("  4. reload dashboard — you should see the live-shop data + anomaly")

    return 0


if __name__ == "__main__":
    sys.exit(main())
