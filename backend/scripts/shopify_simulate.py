"""Synthetischer Shopify-Plus-Datensatz für die End-to-End-Demo.

Erzeugt einen plausiblen DTC-Apparel-Brand (CHF ~30 Mio. Umsatz) mit:
- 200 Produkten (5 Kategorien x 4 Lines x variierende Preise)
- 800 Kunden (mit realistischer Wiederkauf-Verteilung)
- ~5'000 Bestellungen über 120 Tage
- AOV ~CHF 95 (in BRL gespeichert weil Shopify pro Shop eine Währung
  fixiert; Frontend kann das später per CHF-Conversion umrechnen — wir
  bleiben hier in der Shop-Original-Währung)

DELIBERATE ANOMALIE: in den letzten 14 Tagen sinkt der Anteil
Mobile-Quellbestellungen + AOV um ~25 % — Ground-Truth für die
Anomaly-Detector + Investigator-Demo.

Schreibt direkt in raw.shopify_* (idempotent: löscht vorher den
synthetischen Bestand, der per Prefix `sim_` erkennbar ist). Ein
realer Shopify-Sync später kann parallel laufen, sich die Tabellen
also teilen, ohne sich gegenseitig zu beeinträchtigen.

Usage:
    uv run python scripts/shopify_simulate.py
    uv run python scripts/shopify_simulate.py --reset       # wipe sim data first
    uv run python scripts/shopify_simulate.py --days 180    # custom horizon
"""

from __future__ import annotations

import argparse
import json
import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from biq.db import engine

# ---- Catalog --------------------------------------------------------------

CATEGORIES = [
    ("Hoodies", ["Essential", "Oversized", "Tech", "Cropped"]),
    ("Tees", ["Classic", "Heavyweight", "Striped", "Graphic"]),
    ("Pants", ["Wide", "Slim", "Cargo", "Tech"]),
    ("Accessoires", ["Beanie", "Socks", "Bag", "Cap"]),
    ("Outerwear", ["Puffer", "Shell", "Coach", "Anorak"]),
]

PRICE_BY_CATEGORY = {
    "Hoodies": (89, 159),
    "Tees": (39, 69),
    "Pants": (99, 179),
    "Accessoires": (19, 59),
    "Outerwear": (199, 399),
}

CHANNELS = ["web", "ios_app", "android_app", "pos", "draft_order"]
CHANNEL_WEIGHTS = [0.62, 0.15, 0.12, 0.08, 0.03]

COUNTRY_WEIGHTS = [("CH", 0.55), ("DE", 0.30), ("AT", 0.08), ("FR", 0.04), ("IT", 0.03)]


# ---- Reset helpers --------------------------------------------------------


def _wipe_simulated_rows() -> None:
    """Entfernt nur die synth-Datensätze (ID-Prefix 'sim_'); ein echter
    Sync mit Shopify-IDs bleibt erhalten."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM raw.shopify_orders WHERE order_id LIKE 'sim_%'"))
        conn.execute(text("DELETE FROM raw.shopify_customers WHERE customer_id LIKE 'sim_%'"))
        conn.execute(text("DELETE FROM raw.shopify_products WHERE product_id LIKE 'sim_%'"))
        conn.execute(text("DELETE FROM raw.shopify_sync_log WHERE since_iso = 'simulator'"))


# ---- Generators -----------------------------------------------------------


def _generate_products(rng: random.Random) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    pid = 0
    for cat, lines in CATEGORIES:
        low, high = PRICE_BY_CATEGORY[cat]
        for line in lines:
            for variant in range(rng.randint(8, 12)):
                pid += 1
                price = round(rng.uniform(low, high), 2)
                products.append(
                    {
                        "product_id": f"sim_product_{pid:04d}",
                        "title": f"{line} {cat[:-1]} #{variant + 1}",
                        "handle": f"{line.lower()}-{cat.lower()}-{variant + 1}",
                        "vendor": "House Brand",
                        "product_type": cat,
                        "status": "active",
                        "_price": price,  # used internally, not a column
                    }
                )
    return products


def _generate_customers(rng: random.Random, n: int) -> list[dict[str, Any]]:
    customers: list[dict[str, Any]] = []
    for i in range(1, n + 1):
        country = rng.choices(
            [c for c, _ in COUNTRY_WEIGHTS],
            weights=[w for _, w in COUNTRY_WEIGHTS],
        )[0]
        accepts_marketing = rng.random() < 0.62
        # Power-law-like order distribution: most customers buy 1-2 times,
        # a small tail buys 5-20 times. Used at order-generation time.
        propensity = max(1, int(rng.paretovariate(2.0)))
        customers.append(
            {
                "customer_id": f"sim_cust_{i:05d}",
                "email": f"sim+{i:05d}@example.local",
                "state": "enabled",
                "accepts_marketing": accepts_marketing,
                "default_address_country": country,
                "default_address_province": None,
                "_propensity": propensity,
            }
        )
    return customers


def _generate_orders(
    rng: random.Random,
    products: list[dict[str, Any]],
    customers: list[dict[str, Any]],
    days: int,
) -> list[dict[str, Any]]:
    """Streut Bestellungen über die letzten `days` Tage, mit Wochenend-
    und Monatsanfangs-Saisonalität + Mobile-Drop-Anomalie in den letzten
    14 Tagen."""
    now = datetime.now(UTC)
    orders: list[dict[str, Any]] = []
    order_no = 1000

    # Gewicht pro Kunde: höhere _propensity → grössere Auswahl
    expanded_customers: list[dict[str, Any]] = []
    for c in customers:
        for _ in range(c["_propensity"]):
            expanded_customers.append(c)

    for day_offset in range(days):
        date = now - timedelta(days=day_offset)
        weekday = date.weekday()

        # Baseline: ~40 Bestellungen/Tag, +25 % am Wochenende, +15 %
        # am Monatsanfang
        base = 40
        if weekday >= 5:
            base = int(base * 1.25)
        if date.day <= 3:
            base = int(base * 1.15)

        # ANOMALIE: in den letzten 14 Tagen 25 % weniger Bestellungen
        # über Mobile (ios_app + android_app)
        anomaly_window = day_offset < 14

        orders_today = base + rng.randint(-10, 10)

        for _ in range(max(0, orders_today)):
            customer = rng.choice(expanded_customers)
            # Mobile-Bestellungen werden in der Anomalie-Periode halbiert
            channel = rng.choices(CHANNELS, weights=CHANNEL_WEIGHTS)[0]
            if (
                anomaly_window
                and channel in ("ios_app", "android_app")
                and rng.random() < 0.65
            ):
                # 65 % der Mobile-Bestellungen verschwinden in der Anomalie-Periode
                # (sichtbare Anomalie >> Detektor-Threshold 20 %)
                continue

            n_items = rng.choices([1, 2, 3, 4, 5], weights=[0.5, 0.25, 0.15, 0.07, 0.03])[0]
            picked = rng.sample(products, k=min(n_items, len(products)))
            subtotal = sum(p["_price"] for p in picked)

            # ~10 % der Bestellungen mit Rabatt
            discount = round(subtotal * rng.uniform(0.05, 0.20), 2) if rng.random() < 0.10 else 0.0
            shipping = 7.90 if subtotal < 100 else 0.0
            tax = round((subtotal - discount) * 0.077, 2)
            total = round(subtotal - discount + shipping + tax, 2)

            # ~3 % Storno
            financial_status = "paid"
            fulfillment_status = "fulfilled"
            cancelled_at = None
            if rng.random() < 0.03:
                financial_status = "refunded"
                fulfillment_status = None
                cancelled_at = date + timedelta(hours=rng.randint(2, 72))

            order_no += 1
            order_id = f"sim_order_{order_no:07d}"
            line_items = [
                {
                    "id": f"sim_li_{order_no}_{i}",
                    "product_id": p["product_id"],
                    "title": p["title"],
                    "price": str(p["_price"]),
                    "quantity": 1,
                }
                for i, p in enumerate(picked)
            ]

            order = {
                "order_id": order_id,
                "order_number": str(order_no),
                "created_at": date,
                "updated_at": cancelled_at or date,
                "processed_at": date,
                "cancelled_at": cancelled_at,
                "customer_id": customer["customer_id"],
                "email": customer["email"],
                "financial_status": financial_status,
                "fulfillment_status": fulfillment_status,
                "total_price": total,
                "subtotal_price": subtotal,
                "total_discounts": discount,
                "total_shipping": shipping,
                "total_tax": tax,
                "currency": "CHF",
                "line_items_count": len(line_items),
                "source_name": channel,
                "raw": {
                    "id": order_id,
                    "name": f"#{order_no}",
                    "line_items": line_items,
                    "source_name": channel,
                    "customer": {"id": customer["customer_id"]},
                    "_simulated": True,
                },
            }
            orders.append(order)

    return orders


# ---- Persistence ----------------------------------------------------------


def _insert_products(products: list[dict[str, Any]]) -> None:
    with engine.begin() as conn:
        for p in products:
            payload = {
                "product_id": p["product_id"],
                "title": p["title"],
                "handle": p["handle"],
                "vendor": p["vendor"],
                "product_type": p["product_type"],
                "created_at": datetime.now(UTC) - timedelta(days=365),
                "updated_at": datetime.now(UTC),
                "published_at": datetime.now(UTC) - timedelta(days=365),
                "status": p["status"],
                "raw": json.dumps(
                    {k: v for k, v in p.items() if not k.startswith("_")} | {"_simulated": True},
                    default=str,
                ),
            }
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
                    ON CONFLICT (product_id) DO NOTHING
                    """
                ),
                payload,
            )


def _insert_customers(customers: list[dict[str, Any]]) -> None:
    with engine.begin() as conn:
        for c in customers:
            payload = {
                "customer_id": c["customer_id"],
                "email": c["email"],
                "created_at": datetime.now(UTC) - timedelta(days=365),
                "updated_at": datetime.now(UTC),
                "orders_count": 0,
                "total_spent": 0.0,
                "state": c["state"],
                "accepts_marketing": c["accepts_marketing"],
                "default_address_country": c["default_address_country"],
                "default_address_province": c["default_address_province"],
                "raw": json.dumps(
                    {k: v for k, v in c.items() if not k.startswith("_")} | {"_simulated": True},
                    default=str,
                ),
            }
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
                    ON CONFLICT (customer_id) DO NOTHING
                    """
                ),
                payload,
            )


def _insert_orders(orders: list[dict[str, Any]]) -> None:
    with engine.begin() as conn:
        for o in orders:
            payload = dict(o)
            payload["raw"] = json.dumps(o["raw"], default=str)
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
                    ON CONFLICT (order_id) DO NOTHING
                    """
                ),
                payload,
            )


def _refresh_customer_stats() -> None:
    """Aktualisiert orders_count + total_spent in shopify_customers
    aus den eingespielten Bestellungen — wie es Shopify selbst tut."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE raw.shopify_customers c
                SET orders_count = sub.orders,
                    total_spent  = sub.spent
                FROM (
                    SELECT customer_id,
                           COUNT(*)::int                                  AS orders,
                           COALESCE(SUM(total_price), 0)::numeric(14, 2)  AS spent
                    FROM raw.shopify_orders
                    WHERE cancelled_at IS NULL
                    GROUP BY customer_id
                ) AS sub
                WHERE c.customer_id = sub.customer_id
                """
            )
        )


def _log_sync(entity: str, count: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO raw.shopify_sync_log
                    (sync_id, entity, started_at, finished_at, rows_upserted, since_iso)
                VALUES (:id, :entity, now(), now(), :rows, 'simulator')
                """
            ),
            {"id": str(uuid.uuid4()), "entity": entity, "rows": count},
        )


# ---- Main ----------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic Shopify-Plus data generator")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Wipe existing simulated rows before generating new ones.",
    )
    parser.add_argument("--days", type=int, default=120, help="History window in days.")
    parser.add_argument("--customers", type=int, default=800)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)

    if args.reset:
        print("→ Lösche bestehende synth-Daten (sim_*) …")
        _wipe_simulated_rows()

    print(f"→ Generiere Katalog ({sum(len(lines) for _, lines in CATEGORIES) * 10}-15 Varianten/Linie) …")
    products = _generate_products(rng)
    _insert_products(products)
    _log_sync("products", len(products))
    print(f"   {len(products)} Produkte eingefügt")

    print(f"→ Generiere {args.customers} Kunden mit Power-Law-Bestellverteilung …")
    customers = _generate_customers(rng, args.customers)
    _insert_customers(customers)
    _log_sync("customers", len(customers))
    print(f"   {len(customers)} Kunden eingefügt")

    print(f"→ Generiere Bestellungen über {args.days} Tage (inkl. Mobile-Anomalie letzte 14 Tage) …")
    orders = _generate_orders(rng, products, customers, args.days)
    _insert_orders(orders)
    _log_sync("orders", len(orders))
    print(f"   {len(orders)} Bestellungen eingefügt")

    print("→ Aktualisiere Kunden-Statistiken …")
    _refresh_customer_stats()

    print()
    print("Fertig. Live in der DB:")
    with engine.connect() as conn:
        for entity, tbl in [
            ("products", "raw.shopify_products"),
            ("customers", "raw.shopify_customers"),
            ("orders", "raw.shopify_orders"),
        ]:
            total = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar_one()
            sim = conn.execute(
                text(f"SELECT COUNT(*) FROM {tbl} WHERE {entity.rstrip('s')}_id LIKE 'sim_%'")
            ).scalar_one()
            print(f"  {entity:10s} total: {total:>6}   davon synth: {sim:>6}")


if __name__ == "__main__":
    main()
