"""Load Olist CSVs into raw.* tables.

Usage:
    uv run python scripts/load_olist.py
    uv run python scripts/load_olist.py --data-dir ../data/seed
    uv run python scripts/load_olist.py --truncate
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from biq.db import engine

# Order matters: foreign keys flow downward.
# (csv_filename, schema, table, column_mapping_csv_to_db)
TABLES: list[tuple[str, str, str, dict[str, str]]] = [
    (
        "olist_customers_dataset.csv",
        "raw",
        "customers",
        {
            "customer_id": "customer_id",
            "customer_unique_id": "customer_unique_id",
            "customer_zip_code_prefix": "customer_zip_prefix",
            "customer_city": "customer_city",
            "customer_state": "customer_state",
        },
    ),
    (
        "olist_sellers_dataset.csv",
        "raw",
        "sellers",
        {
            "seller_id": "seller_id",
            "seller_zip_code_prefix": "seller_zip_prefix",
            "seller_city": "seller_city",
            "seller_state": "seller_state",
        },
    ),
    (
        "olist_products_dataset.csv",
        "raw",
        "products",
        {
            "product_id": "product_id",
            "product_category_name": "category",
            # Olist ships these with a misspelling — preserve it on the CSV side.
            "product_name_lenght": "product_name_length",
            "product_description_lenght": "product_description_len",
            "product_photos_qty": "photos_qty",
            "product_weight_g": "weight_g",
            "product_length_cm": "length_cm",
            "product_height_cm": "height_cm",
            "product_width_cm": "width_cm",
        },
    ),
    (
        "olist_orders_dataset.csv",
        "raw",
        "orders",
        {
            "order_id": "order_id",
            "customer_id": "customer_id",
            "order_status": "order_status",
            "order_purchase_timestamp": "purchase_ts",
            "order_approved_at": "approved_ts",
            "order_delivered_carrier_date": "delivered_carrier_ts",
            "order_delivered_customer_date": "delivered_customer_ts",
            "order_estimated_delivery_date": "estimated_delivery_ts",
        },
    ),
    (
        "olist_order_items_dataset.csv",
        "raw",
        "order_items",
        {
            "order_id": "order_id",
            "order_item_id": "item_seq",
            "product_id": "product_id",
            "seller_id": "seller_id",
            "shipping_limit_date": "shipping_limit",
            "price": "price",
            "freight_value": "freight",
        },
    ),
    (
        "olist_order_payments_dataset.csv",
        "raw",
        "payments",
        {
            "order_id": "order_id",
            "payment_sequential": "payment_seq",
            "payment_type": "payment_type",
            "payment_installments": "installments",
            "payment_value": "value",
        },
    ),
    (
        "olist_order_reviews_dataset.csv",
        "raw",
        "reviews",
        {
            "review_id": "review_id",
            "order_id": "order_id",
            "review_score": "score",
            "review_comment_title": "comment_title",
            "review_comment_message": "comment_text",
            "review_creation_date": "created_ts",
            "review_answer_timestamp": "answered_ts",
        },
    ),
]


def truncate_all() -> None:
    """Truncate every raw.* table in reverse FK order."""
    targets = ", ".join(f"{schema}.{table}" for _, schema, table, _ in reversed(TABLES))
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {targets} CASCADE"))
    print(f"Truncated: {targets}")


def load_one(csv_path: Path, schema: str, table: str, mapping: dict[str, str]) -> int:
    df = pd.read_csv(csv_path)
    missing = [c for c in mapping if c not in df.columns]
    if missing:
        raise ValueError(f"{csv_path.name}: missing columns {missing}")

    df = df.rename(columns=mapping)[list(mapping.values())]

    # Olist reviews has duplicate review_ids; keep the first.
    if table == "reviews":
        before = len(df)
        df = df.drop_duplicates(subset=["review_id"], keep="first")
        if before != len(df):
            print(f"  deduped {before - len(df)} duplicate review_ids")

    df.to_sql(
        table,
        engine,
        schema=schema,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=1000,
    )
    return len(df)


def load_all(data_dir: Path) -> None:
    if not data_dir.exists():
        raise SystemExit(f"Data directory {data_dir} does not exist")

    for filename, schema, table, mapping in TABLES:
        path = data_dir / filename
        if not path.exists():
            print(f"SKIP {filename}: not found in {data_dir}")
            continue

        print(f"Loading {filename} -> {schema}.{table}")
        rows = load_one(path, schema, table, mapping)
        print(f"  {rows:,} rows")

    print("\nDone.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Olist CSVs into raw.* tables")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent / "data" / "seed",
        help="Directory containing the Olist CSV files",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Truncate all raw.* tables before loading",
    )
    args = parser.parse_args()

    if args.truncate:
        truncate_all()
    load_all(args.data_dir)


if __name__ == "__main__":
    main()
