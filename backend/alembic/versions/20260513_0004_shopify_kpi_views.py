"""shopify kpi views

Vier Manager-relevante Views über raw.shopify_* — strukturell parallel
zur kpi.* Surface die der Olist-Pfad nutzt, damit Anomaly-Detector,
Investigator und Frontend keine Spezialfälle brauchen.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-13
"""

from __future__ import annotations

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
        -- Tagesumsätze + AOV pro Akquisitions-Kanal (Mapping channel <- source_name)
        CREATE OR REPLACE VIEW kpi.shopify_orders_daily AS
        SELECT
            DATE(created_at)                                       AS day,
            CASE
                WHEN source_name IN ('ios_app', 'android_app') THEN 'mobile'
                WHEN source_name = 'web'                       THEN 'desktop'
                WHEN source_name = 'pos'                       THEN 'pos'
                ELSE 'other'
            END                                                    AS channel,
            COUNT(*)                                               AS orders,
            COUNT(*) FILTER (WHERE cancelled_at IS NULL)           AS orders_completed,
            SUM(total_price)::numeric(14, 2)                       AS revenue,
            AVG(total_price)::numeric(10, 2)                       AS aov,
            SUM(line_items_count)                                  AS items_total
        FROM raw.shopify_orders
        GROUP BY 1, 2;

        -- AOV-fokussierte View (täglich, pro Channel) — manche Manager
        -- wollen das prominent als eigene Karte
        CREATE OR REPLACE VIEW kpi.shopify_aov_daily AS
        SELECT
            day,
            channel,
            aov::numeric                                            AS aov_chf,
            orders_completed,
            revenue
        FROM kpi.shopify_orders_daily;

        -- Wöchentliche Rückgabequote: Anteil refunded / cancelled
        CREATE OR REPLACE VIEW kpi.shopify_refund_rate_weekly AS
        SELECT
            DATE_TRUNC('week', created_at)::date                   AS week,
            CASE
                WHEN source_name IN ('ios_app', 'android_app') THEN 'mobile'
                WHEN source_name = 'web'                       THEN 'desktop'
                WHEN source_name = 'pos'                       THEN 'pos'
                ELSE 'other'
            END                                                    AS channel,
            COUNT(*)                                               AS orders,
            COUNT(*) FILTER (
                WHERE financial_status = 'refunded'
                   OR cancelled_at IS NOT NULL
            )                                                      AS refunded,
            (COUNT(*) FILTER (
                WHERE financial_status = 'refunded'
                   OR cancelled_at IS NOT NULL
            )::float
             / NULLIF(COUNT(*), 0) * 100)::numeric(6, 2)            AS refund_rate_pct
        FROM raw.shopify_orders
        GROUP BY 1, 2;

        -- Wiederkäufer-Rate pro Woche: Anteil Kunden mit >= 2 Bestellungen
        -- innerhalb von 90 Tagen ab erster Bestellung
        CREATE OR REPLACE VIEW kpi.shopify_repeat_rate_weekly AS
        WITH first_order AS (
            SELECT
                customer_id,
                MIN(created_at)                                    AS first_at
            FROM raw.shopify_orders
            WHERE cancelled_at IS NULL
              AND customer_id IS NOT NULL
            GROUP BY customer_id
        ),
        cohort AS (
            SELECT
                f.customer_id,
                DATE_TRUNC('week', f.first_at)::date                AS cohort_week,
                COUNT(o.order_id)                                   AS orders_in_90d
            FROM first_order f
            JOIN raw.shopify_orders o
              ON o.customer_id = f.customer_id
             AND o.created_at BETWEEN f.first_at AND f.first_at + INTERVAL '90 days'
             AND o.cancelled_at IS NULL
            GROUP BY f.customer_id, cohort_week
        )
        SELECT
            cohort_week                                            AS week,
            COUNT(*)                                               AS customers,
            COUNT(*) FILTER (WHERE orders_in_90d >= 2)             AS repeaters,
            (COUNT(*) FILTER (WHERE orders_in_90d >= 2)::float
             / NULLIF(COUNT(*), 0) * 100)::numeric(6, 2)            AS repeat_rate_pct
        FROM cohort
        GROUP BY cohort_week;
    """)


def downgrade() -> None:
    op.execute("""
        DROP VIEW IF EXISTS kpi.shopify_repeat_rate_weekly;
        DROP VIEW IF EXISTS kpi.shopify_refund_rate_weekly;
        DROP VIEW IF EXISTS kpi.shopify_aov_daily;
        DROP VIEW IF EXISTS kpi.shopify_orders_daily;
    """)
