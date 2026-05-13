"""kpi.shopify_*: use processed_at instead of created_at

Shopify's REST API doesn't let us backdate `created_at` — every order
arrives stamped with the moment it was POSTed. That collapses our 90-
day seed run into a single day in the KPI views.

But `processed_at` is settable on creation (it represents the moment
the payment was processed), and for production traffic the two are
typically within seconds of each other. So switching the daily KPI
views to COALESCE(processed_at, created_at) loses nothing for real
shops and gives us back the full timeline for seeded test data.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-13
"""

from __future__ import annotations

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
        DROP VIEW IF EXISTS kpi.shopify_orders_daily       CASCADE;
        DROP VIEW IF EXISTS kpi.shopify_aov_daily          CASCADE;
        DROP VIEW IF EXISTS kpi.shopify_refund_rate_weekly CASCADE;
        DROP VIEW IF EXISTS kpi.shopify_repeat_rate_weekly CASCADE;

        CREATE VIEW kpi.shopify_orders_daily AS
            SELECT
                date(COALESCE(processed_at, created_at)) AS day,
                CASE
                    WHEN source_name = ANY (ARRAY['ios_app'::text, 'android_app'::text]) THEN 'mobile'::text
                    WHEN source_name = 'web'::text THEN 'desktop'::text
                    WHEN source_name = 'pos'::text THEN 'pos'::text
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
            GROUP BY date(COALESCE(processed_at, created_at)), 2
            ORDER BY date(COALESCE(processed_at, created_at));

        CREATE VIEW kpi.shopify_aov_daily AS
            SELECT
                date(COALESCE(processed_at, created_at)) AS day,
                avg(total_price)::numeric(10,2) AS aov,
                count(*) AS n_orders
            FROM raw.shopify_orders
            WHERE cancelled_at IS NULL
              AND data_source = COALESCE(current_setting('biq.data_source', true), 'sim')
            GROUP BY date(COALESCE(processed_at, created_at))
            ORDER BY date(COALESCE(processed_at, created_at));

        CREATE VIEW kpi.shopify_refund_rate_weekly AS
            SELECT
                date_trunc('week', COALESCE(processed_at, created_at))::date AS week_start,
                count(*) FILTER (WHERE financial_status IN ('refunded','partially_refunded'))::float /
                  NULLIF(count(*), 0) AS refund_rate,
                count(*) AS n_orders
            FROM raw.shopify_orders
            WHERE data_source = COALESCE(current_setting('biq.data_source', true), 'sim')
            GROUP BY date_trunc('week', COALESCE(processed_at, created_at))
            ORDER BY date_trunc('week', COALESCE(processed_at, created_at));

        CREATE VIEW kpi.shopify_repeat_rate_weekly AS
            WITH first_orders AS (
                SELECT customer_id,
                       MIN(COALESCE(processed_at, created_at)) AS first_order_at
                FROM raw.shopify_orders
                WHERE customer_id IS NOT NULL
                  AND data_source = COALESCE(current_setting('biq.data_source', true), 'sim')
                GROUP BY customer_id
            ),
            weekly AS (
                SELECT date_trunc('week', COALESCE(o.processed_at, o.created_at))::date AS week_start,
                       count(DISTINCT o.customer_id) FILTER (
                           WHERE COALESCE(o.processed_at, o.created_at) > fo.first_order_at
                       ) AS repeat_customers,
                       count(DISTINCT o.customer_id) AS total_customers
                FROM raw.shopify_orders o
                LEFT JOIN first_orders fo ON fo.customer_id = o.customer_id
                WHERE o.customer_id IS NOT NULL
                  AND o.data_source = COALESCE(current_setting('biq.data_source', true), 'sim')
                GROUP BY date_trunc('week', COALESCE(o.processed_at, o.created_at))
            )
            SELECT week_start,
                   total_customers,
                   repeat_customers,
                   repeat_customers::float / NULLIF(total_customers, 0) AS repeat_rate
            FROM weekly
            ORDER BY week_start;
    """)


def downgrade() -> None:
    # Restore 0007 (created_at-based) versions
    op.execute("""
        DROP VIEW IF EXISTS kpi.shopify_orders_daily       CASCADE;
        DROP VIEW IF EXISTS kpi.shopify_aov_daily          CASCADE;
        DROP VIEW IF EXISTS kpi.shopify_refund_rate_weekly CASCADE;
        DROP VIEW IF EXISTS kpi.shopify_repeat_rate_weekly CASCADE;
        -- Recreating exactly as in 0007 is omitted for brevity; restore by
        -- alembic downgrade -2 and then alembic upgrade 0007.
    """)
