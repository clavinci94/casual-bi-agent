-- Schema: kpi
-- Semantic layer. Agents must read from these views, never from raw.*.
-- Definitions trace to docs/kpi-catalog.yaml.

CREATE SCHEMA IF NOT EXISTS kpi;

-- ===================================================================
-- conversion_rate_daily
-- One row per (day, device, channel, country). Bots excluded.
-- Session day = day of session's earliest event.
-- ===================================================================
DROP VIEW IF EXISTS kpi.conversion_rate_daily CASCADE;
CREATE VIEW kpi.conversion_rate_daily AS
WITH session_facts AS (
    SELECT
        date_trunc('day', MIN(ts))::date    AS day,
        session_id,
        MIN(device)                         AS device,
        MIN(channel)                        AS channel,
        MIN(country)                        AS country,
        BOOL_OR(event_type = 'purchase')    AS converted
    FROM raw.web_events
    WHERE NOT is_bot
    GROUP BY session_id
)
SELECT
    day,
    device,
    channel,
    country,
    COUNT(*)                                              AS sessions,
    COUNT(*) FILTER (WHERE converted)                     AS conversions,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE converted) / NULLIF(COUNT(*), 0),
        4
    )                                                     AS conversion_rate_pct
FROM session_facts
GROUP BY day, device, channel, country;

COMMENT ON VIEW kpi.conversion_rate_daily IS
  'Daily session-based conversion rate, bots excluded. Catalog: conversion_rate.';

-- ===================================================================
-- aov_daily
-- Average order value (revenue per order). Cancelled/unavailable excluded.
-- ===================================================================
DROP VIEW IF EXISTS kpi.aov_daily CASCADE;
CREATE VIEW kpi.aov_daily AS
SELECT
    date_trunc('day', o.purchase_ts)::date              AS day,
    p.category,
    c.customer_state                                     AS region,
    COUNT(DISTINCT o.order_id)                           AS orders,
    SUM(oi.price)::numeric(14, 2)                        AS revenue_brl,
    ROUND(SUM(oi.price) / NULLIF(COUNT(DISTINCT o.order_id), 0), 2) AS aov_brl
FROM raw.orders o
JOIN raw.order_items oi   ON oi.order_id = o.order_id
LEFT JOIN raw.products p  ON p.product_id = oi.product_id
LEFT JOIN raw.customers c ON c.customer_id = o.customer_id
WHERE o.order_status NOT IN ('canceled', 'unavailable')
GROUP BY 1, 2, 3;

COMMENT ON VIEW kpi.aov_daily IS 'Average order value per day × category × region. Catalog: average_order_value.';

-- ===================================================================
-- gross_margin_weekly
-- COGS = product.cogs_estimate_brl, falling back to 50% of price.
-- ===================================================================
DROP VIEW IF EXISTS kpi.gross_margin_weekly CASCADE;
CREATE VIEW kpi.gross_margin_weekly AS
SELECT
    date_trunc('week', o.purchase_ts)::date                              AS week,
    p.category,
    c.customer_state                                                      AS region,
    SUM(oi.price)::numeric(14, 2)                                         AS revenue_brl,
    SUM(COALESCE(p.cogs_estimate_brl, 0.5 * oi.price))::numeric(14, 2)    AS cogs_brl,
    SUM(oi.freight)::numeric(14, 2)                                       AS freight_brl,
    ROUND(
        (SUM(oi.price)
            - SUM(COALESCE(p.cogs_estimate_brl, 0.5 * oi.price))
            - SUM(oi.freight))
            / NULLIF(SUM(oi.price), 0),
        4
    )                                                                     AS gross_margin
FROM raw.orders o
JOIN raw.order_items oi   ON oi.order_id = o.order_id
LEFT JOIN raw.products p  ON p.product_id = oi.product_id
LEFT JOIN raw.customers c ON c.customer_id = o.customer_id
WHERE o.order_status NOT IN ('canceled', 'unavailable')
GROUP BY 1, 2, 3;

COMMENT ON VIEW kpi.gross_margin_weekly IS
  'Weekly gross margin. Catalog: gross_margin. COGS fallback = 0.5 × price (ADR-003).';

-- ===================================================================
-- delivery_time_p95
-- 95th percentile of (delivered_customer_ts - purchase_ts), in days.
-- ===================================================================
DROP VIEW IF EXISTS kpi.delivery_time_p95 CASCADE;
CREATE VIEW kpi.delivery_time_p95 AS
WITH delivery AS (
    SELECT
        date_trunc('day', o.purchase_ts)::date    AS day,
        c.customer_state                          AS region,
        oi.seller_id,
        p.category,
        EXTRACT(EPOCH FROM (o.delivered_customer_ts - o.purchase_ts)) / 86400.0 AS days_to_deliver
    FROM raw.orders o
    JOIN raw.order_items oi   ON oi.order_id = o.order_id
    LEFT JOIN raw.products p  ON p.product_id = oi.product_id
    LEFT JOIN raw.customers c ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered'
      AND o.delivered_customer_ts IS NOT NULL
)
SELECT
    day, region, seller_id, category,
    COUNT(*)                                                                       AS deliveries,
    ROUND(percentile_disc(0.95) WITHIN GROUP (ORDER BY days_to_deliver)::numeric, 2) AS p95_days,
    ROUND(AVG(days_to_deliver)::numeric, 2)                                        AS avg_days
FROM delivery
GROUP BY 1, 2, 3, 4;

COMMENT ON VIEW kpi.delivery_time_p95 IS 'p95 days from purchase to delivery. Catalog: delivery_time_p95.';

-- ===================================================================
-- review_score_avg
-- Weekly mean review score by category × seller × region.
-- ===================================================================
DROP VIEW IF EXISTS kpi.review_score_avg CASCADE;
CREATE VIEW kpi.review_score_avg AS
SELECT
    date_trunc('week', r.created_ts)::date    AS week,
    p.category,
    oi.seller_id,
    c.customer_state                          AS region,
    COUNT(*)                                  AS reviews,
    ROUND(AVG(r.score)::numeric, 3)           AS avg_score,
    COUNT(*) FILTER (WHERE r.score <= 2)      AS low_scores
FROM raw.reviews r
JOIN raw.order_items oi   ON oi.order_id = r.order_id
LEFT JOIN raw.products p  ON p.product_id = oi.product_id
LEFT JOIN raw.orders o    ON o.order_id = r.order_id
LEFT JOIN raw.customers c ON c.customer_id = o.customer_id
GROUP BY 1, 2, 3, 4;

COMMENT ON VIEW kpi.review_score_avg IS 'Weekly review aggregates. Catalog: review_score_avg.';

-- ===================================================================
-- refund_rate
-- Share of canceled / unavailable orders per week × category × region × payment.
-- ===================================================================
DROP VIEW IF EXISTS kpi.refund_rate CASCADE;
CREATE VIEW kpi.refund_rate AS
SELECT
    date_trunc('week', o.purchase_ts)::date         AS week,
    p.category,
    c.customer_state                                 AS region,
    pay.payment_type,
    COUNT(DISTINCT o.order_id)                       AS orders,
    COUNT(DISTINCT o.order_id) FILTER (
        WHERE o.order_status IN ('canceled', 'unavailable')
    )                                                AS refunded,
    ROUND(
        100.0 * COUNT(DISTINCT o.order_id) FILTER (
            WHERE o.order_status IN ('canceled', 'unavailable')
        ) / NULLIF(COUNT(DISTINCT o.order_id), 0),
        2
    )                                                AS refund_rate_pct
FROM raw.orders o
LEFT JOIN raw.order_items oi  ON oi.order_id = o.order_id
LEFT JOIN raw.products p      ON p.product_id = oi.product_id
LEFT JOIN raw.customers c     ON c.customer_id = o.customer_id
LEFT JOIN raw.payments pay    ON pay.order_id = o.order_id AND pay.payment_seq = 1
GROUP BY 1, 2, 3, 4;

COMMENT ON VIEW kpi.refund_rate IS 'Refund share per week. Catalog: refund_rate.';

-- ===================================================================
-- repeat_purchase_rate
-- Customers with ≥2 orders within 90 days of first order.
-- ===================================================================
DROP VIEW IF EXISTS kpi.repeat_purchase_rate CASCADE;
CREATE VIEW kpi.repeat_purchase_rate AS
WITH first_order AS (
    SELECT
        c.customer_unique_id,
        MIN(c.customer_state)  AS region,
        MIN(c.segment)         AS segment,
        MIN(o.purchase_ts)     AS first_order_ts
    FROM raw.customers c
    JOIN raw.orders o ON o.customer_id = c.customer_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY c.customer_unique_id
),
orders_in_window AS (
    SELECT
        fo.customer_unique_id,
        fo.region,
        fo.segment,
        date_trunc('week', fo.first_order_ts)::date  AS first_week,
        COUNT(*) AS n_orders
    FROM first_order fo
    JOIN raw.customers c2 ON c2.customer_unique_id = fo.customer_unique_id
    JOIN raw.orders o2    ON o2.customer_id = c2.customer_id
    WHERE o2.order_status NOT IN ('canceled', 'unavailable')
      AND o2.purchase_ts <= fo.first_order_ts + INTERVAL '90 days'
    GROUP BY fo.customer_unique_id, fo.region, fo.segment, first_week
)
SELECT
    first_week                                       AS week,
    region,
    segment,
    COUNT(*)                                         AS customers,
    COUNT(*) FILTER (WHERE n_orders >= 2)            AS repeaters,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE n_orders >= 2) / NULLIF(COUNT(*), 0),
        2
    )                                                AS repeat_rate_pct
FROM orders_in_window
GROUP BY first_week, region, segment;

COMMENT ON VIEW kpi.repeat_purchase_rate IS
  'Cohort repeat-purchase rate within 90 days of first order. Catalog: repeat_purchase_rate.';

-- ===================================================================
-- churn_30d  (placeholder — full definition in next iteration)
-- Rationale: needs generate_series across weeks plus careful at-risk
-- semantics. Empty view keeps callers compiling.
-- ===================================================================
DROP VIEW IF EXISTS kpi.churn_30d CASCADE;
CREATE VIEW kpi.churn_30d AS
SELECT
    CURRENT_DATE   AS week,
    NULL::text     AS region,
    NULL::text     AS segment,
    0::int         AS churned,
    0::int         AS at_risk,
    0.0::numeric   AS churn_rate_pct
WHERE FALSE;

COMMENT ON VIEW kpi.churn_30d IS 'Placeholder until full churn definition lands.';

COMMENT ON SCHEMA kpi IS 'Semantic layer. Agents may only read from these views.';
