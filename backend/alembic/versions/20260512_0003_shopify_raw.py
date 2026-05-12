"""shopify raw tables

Lands raw Shopify entities (orders, customers, products) in `raw.shopify_*`
so the rest of the stack — KPI views, anomaly detector, investigator —
can read them through the same `raw.*` semantic surface the Olist data
uses. Full Shopify response stays in a `raw` jsonb column so we can
re-materialise any field later without re-syncing.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-12
"""

from __future__ import annotations

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS raw.shopify_orders (
            order_id            text         PRIMARY KEY,
            order_number        text,
            created_at          timestamptz  NOT NULL,
            updated_at          timestamptz,
            processed_at        timestamptz,
            cancelled_at        timestamptz,
            customer_id         text,
            email               text,
            financial_status    text,
            fulfillment_status  text,
            total_price         numeric(14, 2),
            subtotal_price      numeric(14, 2),
            total_discounts     numeric(14, 2),
            total_shipping      numeric(14, 2),
            total_tax           numeric(14, 2),
            currency            text,
            line_items_count    integer,
            source_name         text,
            raw                 jsonb        NOT NULL,
            synced_at           timestamptz  NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS shopify_orders_created_idx
            ON raw.shopify_orders (created_at);
        CREATE INDEX IF NOT EXISTS shopify_orders_customer_idx
            ON raw.shopify_orders (customer_id);

        CREATE TABLE IF NOT EXISTS raw.shopify_customers (
            customer_id              text         PRIMARY KEY,
            email                    text,
            created_at               timestamptz,
            updated_at               timestamptz,
            orders_count             integer,
            total_spent              numeric(14, 2),
            state                    text,
            accepts_marketing        boolean,
            default_address_country  text,
            default_address_province text,
            raw                      jsonb        NOT NULL,
            synced_at                timestamptz  NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS raw.shopify_products (
            product_id      text         PRIMARY KEY,
            title           text,
            handle          text,
            vendor          text,
            product_type    text,
            created_at      timestamptz,
            updated_at      timestamptz,
            published_at    timestamptz,
            status          text,
            raw             jsonb        NOT NULL,
            synced_at       timestamptz  NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS raw.shopify_sync_log (
            sync_id       text         PRIMARY KEY DEFAULT gen_random_uuid()::text,
            entity        text         NOT NULL,
            started_at    timestamptz  NOT NULL DEFAULT now(),
            finished_at   timestamptz,
            rows_upserted integer,
            error         text,
            since_iso     text
        );
        CREATE INDEX IF NOT EXISTS shopify_sync_log_entity_idx
            ON raw.shopify_sync_log (entity, started_at DESC);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS raw.shopify_sync_log CASCADE;
        DROP TABLE IF EXISTS raw.shopify_products CASCADE;
        DROP TABLE IF EXISTS raw.shopify_customers CASCADE;
        DROP TABLE IF EXISTS raw.shopify_orders CASCADE;
    """)
