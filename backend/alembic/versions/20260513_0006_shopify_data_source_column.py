"""shopify_*: data_source column for sim vs live parallel storage

Adds `data_source text NOT NULL DEFAULT 'live'` to the three raw.shopify_*
tables. Tags existing rows (which all came from shopify_simulate.py) as
'sim'. Subsequent real syncs from the Admin API tag as 'live'.

The four kpi.shopify_* views are re-created with a WHERE-filter against
a custom Postgres session variable `biq.data_source`. Backend sets that
variable on every connection (see biq.db) based on the BIQ_DATA_SOURCE
env var. Flip the env var → flip the dashboard between sim and live
without rebuilding views.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-13
"""

from __future__ import annotations

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # 1. Add the tagging column. Default 'live' so a fresh sync gets the
    # right tag without explicit assignment in the connector.
    op.execute("""
        ALTER TABLE raw.shopify_orders
            ADD COLUMN IF NOT EXISTS data_source text NOT NULL DEFAULT 'live';
        ALTER TABLE raw.shopify_customers
            ADD COLUMN IF NOT EXISTS data_source text NOT NULL DEFAULT 'live';
        ALTER TABLE raw.shopify_products
            ADD COLUMN IF NOT EXISTS data_source text NOT NULL DEFAULT 'live';
    """)

    # 2. Re-tag existing rows as 'sim' — anything already in the DB came
    # from the simulator (we'd never have synced live data yet). The
    # connector will start writing 'live' from the next sync onwards.
    op.execute("""
        UPDATE raw.shopify_orders    SET data_source = 'sim' WHERE data_source = 'live';
        UPDATE raw.shopify_customers SET data_source = 'sim' WHERE data_source = 'live';
        UPDATE raw.shopify_products  SET data_source = 'sim' WHERE data_source = 'live';
    """)

    # 3. Helpful indexes for the filter — small selectivity boost when the
    # tables grow past a few hundred thousand rows.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_shopify_orders_data_source
            ON raw.shopify_orders (data_source);
        CREATE INDEX IF NOT EXISTS idx_shopify_customers_data_source
            ON raw.shopify_customers (data_source);
        CREATE INDEX IF NOT EXISTS idx_shopify_products_data_source
            ON raw.shopify_products (data_source);
    """)

    # 4. Re-create the four kpi.shopify_* views with the data_source
    # filter. Reads the Postgres session var biq.data_source; defaults
    # to 'sim' if unset (safe default — never accidentally show live
    # data in a session that forgot to set the var).
    # DROP first because CREATE VIEW can't change the column
    # list; new views may have added/renamed columns.
    op.execute("""
        DROP VIEW IF EXISTS kpi.shopify_orders_daily       CASCADE;
        DROP VIEW IF EXISTS kpi.shopify_aov_daily          CASCADE;
        DROP VIEW IF EXISTS kpi.shopify_refund_rate_weekly CASCADE;
        DROP VIEW IF EXISTS kpi.shopify_repeat_rate_weekly CASCADE;

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

        CREATE VIEW kpi.shopify_aov_daily AS
            SELECT
                date(created_at) AS day,
                avg(total_price)::numeric(10,2) AS aov,
                count(*) AS n_orders
            FROM raw.shopify_orders
            WHERE cancelled_at IS NULL
              AND data_source = COALESCE(current_setting('biq.data_source', true), 'sim')
            GROUP BY date(created_at)
            ORDER BY date(created_at);

        CREATE VIEW kpi.shopify_refund_rate_weekly AS
            SELECT
                date_trunc('week', created_at)::date AS week_start,
                count(*) FILTER (WHERE financial_status IN ('refunded','partially_refunded'))::float /
                  NULLIF(count(*), 0) AS refund_rate,
                count(*) AS n_orders
            FROM raw.shopify_orders
            WHERE data_source = COALESCE(current_setting('biq.data_source', true), 'sim')
            GROUP BY date_trunc('week', created_at)
            ORDER BY date_trunc('week', created_at);

        CREATE VIEW kpi.shopify_repeat_rate_weekly AS
            WITH first_orders AS (
                SELECT customer_id, MIN(created_at) AS first_order_at
                FROM raw.shopify_orders
                WHERE customer_id IS NOT NULL
                  AND data_source = COALESCE(current_setting('biq.data_source', true), 'sim')
                GROUP BY customer_id
            ),
            weekly AS (
                SELECT date_trunc('week', o.created_at)::date AS week_start,
                       count(DISTINCT o.customer_id) FILTER (
                           WHERE o.created_at > fo.first_order_at
                       ) AS repeat_customers,
                       count(DISTINCT o.customer_id) AS total_customers
                FROM raw.shopify_orders o
                LEFT JOIN first_orders fo ON fo.customer_id = o.customer_id
                WHERE o.customer_id IS NOT NULL
                  AND o.data_source = COALESCE(current_setting('biq.data_source', true), 'sim')
                GROUP BY date_trunc('week', o.created_at)
            )
            SELECT week_start,
                   total_customers,
                   repeat_customers,
                   repeat_customers::float / NULLIF(total_customers, 0) AS repeat_rate
            FROM weekly
            ORDER BY week_start;
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS raw.idx_shopify_orders_data_source;
        DROP INDEX IF EXISTS raw.idx_shopify_customers_data_source;
        DROP INDEX IF EXISTS raw.idx_shopify_products_data_source;
        ALTER TABLE raw.shopify_orders    DROP COLUMN IF EXISTS data_source;
        ALTER TABLE raw.shopify_customers DROP COLUMN IF EXISTS data_source;
        ALTER TABLE raw.shopify_products  DROP COLUMN IF EXISTS data_source;
    """)
