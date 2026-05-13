"""kpi.shopify_orders_daily: derive channel from tags when source_name absent

Shopify protects the `source_name` field — third-party (Custom App)
API clients cannot set it to "web"/"ios_app"/"android_app"/"pos".
Orders created via our seed script therefore arrive with NULL or
"shopify_draft_order" as source_name and would all fall into the
"other" channel bucket, breaking the Mobile-anomaly demo.

Workaround: the seed script writes `channel:mobile`, `channel:desktop`,
`channel:pos` into the order's `tags`. The KPI view here reads tags
as a fallback when source_name doesn't match a known channel.

Real Shopify-Plus stores (not seeded) will always set source_name
correctly via the proper Shopify checkout flow, so the primary path
still works.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-13
"""

from __future__ import annotations

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Tags are stored in raw.shopify_orders.raw->'tags' as a comma-separated
    # string. We inspect that JSON path before falling back to 'other'.
    op.execute("""
        DROP VIEW IF EXISTS kpi.shopify_orders_daily CASCADE;

        CREATE VIEW kpi.shopify_orders_daily AS
            SELECT
                date(created_at) AS day,
                CASE
                    -- Primary: real shop traffic with Shopify-set source_name
                    WHEN source_name = ANY (ARRAY['ios_app'::text, 'android_app'::text]) THEN 'mobile'::text
                    WHEN source_name = 'web'::text THEN 'desktop'::text
                    WHEN source_name = 'pos'::text THEN 'pos'::text
                    -- Fallback: seeded test orders use a tag because the
                    -- Admin API forbids us setting protected source_name values
                    WHEN (raw->>'tags') ILIKE '%channel:mobile%' THEN 'mobile'::text
                    WHEN (raw->>'tags') ILIKE '%channel:desktop%' THEN 'desktop'::text
                    WHEN (raw->>'tags') ILIKE '%channel:pos%' THEN 'pos'::text
                    ELSE 'other'::text
                END AS channel,
                count(*) AS orders,
                count(*) FILTER (WHERE cancelled_at IS NULL) AS orders_completed,
                sum(total_price)::numeric(14,2) AS revenue,
                avg(total_price)::numeric(10,2) AS aov,
                sum(line_items_count) AS items_total
            FROM raw.shopify_orders
            WHERE data_source = COALESCE(current_setting('biq.data_source', true), 'sim')
            GROUP BY date(created_at), 2
            ORDER BY date(created_at);
    """)


def downgrade() -> None:
    # Restore the 0006 definition without the tag fallback
    op.execute("""
        DROP VIEW IF EXISTS kpi.shopify_orders_daily CASCADE;

        CREATE VIEW kpi.shopify_orders_daily AS
            SELECT
                date(created_at) AS day,
                CASE
                    WHEN source_name = ANY (ARRAY['ios_app'::text, 'android_app'::text]) THEN 'mobile'::text
                    WHEN source_name = 'web'::text THEN 'desktop'::text
                    WHEN source_name = 'pos'::text THEN 'pos'::text
                    ELSE 'other'::text
                END AS channel,
                count(*) AS orders,
                count(*) FILTER (WHERE cancelled_at IS NULL) AS orders_completed,
                sum(total_price)::numeric(14,2) AS revenue,
                avg(total_price)::numeric(10,2) AS aov,
                sum(line_items_count) AS items_total
            FROM raw.shopify_orders
            WHERE data_source = COALESCE(current_setting('biq.data_source', true), 'sim')
            GROUP BY date(created_at), 2
            ORDER BY date(created_at);
    """)
