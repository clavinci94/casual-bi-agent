-- Schema: raw
-- Operational source-of-truth: Olist core + simulated extensions.
-- Append-only where possible. Updates only via migrations.
-- Agents must NOT read from raw.* directly — use kpi.* views.

CREATE SCHEMA IF NOT EXISTS raw;

------------------------------------------------------------------
-- Olist core tables
------------------------------------------------------------------

CREATE TABLE raw.customers (
    customer_id          text PRIMARY KEY,
    customer_unique_id   text NOT NULL,
    customer_zip_prefix  text,
    customer_city        text,
    customer_state       text,
    -- enrichment
    segment              text,
    first_order_at       timestamptz,
    loaded_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON raw.customers (customer_unique_id);
CREATE INDEX ON raw.customers (customer_state);

CREATE TABLE raw.sellers (
    seller_id           text PRIMARY KEY,
    seller_zip_prefix   text,
    seller_city         text,
    seller_state        text,
    loaded_at           timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE raw.products (
    product_id              text PRIMARY KEY,
    category                text,
    product_name_length     int,
    product_description_len int,
    photos_qty              int,
    weight_g                int,
    length_cm               int,
    height_cm               int,
    width_cm                int,
    -- estimated cost of goods sold; constant per gram, see ADR-003
    cogs_estimate_brl       numeric(12,2),
    loaded_at               timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON raw.products (category);

CREATE TABLE raw.orders (
    order_id                       text PRIMARY KEY,
    customer_id                    text NOT NULL REFERENCES raw.customers(customer_id),
    order_status                   text NOT NULL,
    purchase_ts                    timestamptz NOT NULL,
    approved_ts                    timestamptz,
    delivered_carrier_ts           timestamptz,
    delivered_customer_ts          timestamptz,
    estimated_delivery_ts          timestamptz,
    loaded_at                      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON raw.orders (customer_id);
CREATE INDEX ON raw.orders (purchase_ts);
CREATE INDEX ON raw.orders (order_status);

CREATE TABLE raw.order_items (
    order_id        text NOT NULL REFERENCES raw.orders(order_id),
    item_seq        int  NOT NULL,
    product_id      text NOT NULL REFERENCES raw.products(product_id),
    seller_id       text NOT NULL REFERENCES raw.sellers(seller_id),
    shipping_limit  timestamptz,
    price           numeric(12,2) NOT NULL,
    freight         numeric(12,2) NOT NULL,
    PRIMARY KEY (order_id, item_seq)
);
CREATE INDEX ON raw.order_items (product_id);
CREATE INDEX ON raw.order_items (seller_id);

CREATE TABLE raw.payments (
    order_id        text NOT NULL REFERENCES raw.orders(order_id),
    payment_seq     int  NOT NULL,
    payment_type    text,
    installments    int,
    value           numeric(12,2) NOT NULL,
    PRIMARY KEY (order_id, payment_seq)
);

CREATE TABLE raw.reviews (
    review_id           text PRIMARY KEY,
    order_id            text NOT NULL REFERENCES raw.orders(order_id),
    score               int  NOT NULL CHECK (score BETWEEN 1 AND 5),
    comment_title       text,
    comment_text        text,
    created_ts          timestamptz NOT NULL,
    answered_ts         timestamptz,
    loaded_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON raw.reviews (order_id);
CREATE INDEX ON raw.reviews (created_ts);

------------------------------------------------------------------
-- Simulated extensions (synthesised from Olist anchors).
-- Reproducible from SIMULATION_SEED env var.
------------------------------------------------------------------

-- Clickstream: needed for conversion rate, attribution, funnel.
CREATE TABLE raw.web_events (
    event_id        bigserial PRIMARY KEY,
    session_id      uuid NOT NULL,
    customer_id     text REFERENCES raw.customers(customer_id),
    ts              timestamptz NOT NULL,
    event_type      text NOT NULL,    -- page_view | add_to_cart | begin_checkout | purchase | error
    page            text,
    product_id      text REFERENCES raw.products(product_id),
    device          text NOT NULL,    -- mobile | desktop | tablet
    channel         text,             -- organic | paid_search | social | email | direct
    campaign_id     text,
    country         text,
    is_bot          boolean NOT NULL DEFAULT false
);
CREATE INDEX ON raw.web_events (session_id);
CREATE INDEX ON raw.web_events (ts);
CREATE INDEX ON raw.web_events (event_type);
CREATE INDEX ON raw.web_events (campaign_id);

-- Marketing campaigns: treatments for causal inference.
CREATE TABLE raw.campaigns (
    campaign_id     text PRIMARY KEY,
    name            text NOT NULL,
    channel         text NOT NULL,
    target_segment  text,
    target_region   text,
    start_ts        timestamptz NOT NULL,
    end_ts          timestamptz,
    budget_brl      numeric(12,2),
    hypothesis      text,
    owner           text
);
CREATE INDEX ON raw.campaigns (start_ts);

-- Release / deploy log: more treatments (e.g. mobile_checkout_v2 regression).
CREATE TABLE raw.releases (
    release_id      text PRIMARY KEY,
    component       text NOT NULL,    -- mobile_checkout | desktop_checkout | search | recs | ...
    version         text NOT NULL,
    released_ts     timestamptz NOT NULL,
    rollback_ts     timestamptz,
    notes           text
);

-- Support tickets: unstructured signal source.
CREATE TABLE raw.support_tickets (
    ticket_id       text PRIMARY KEY,
    customer_id     text REFERENCES raw.customers(customer_id),
    order_id        text REFERENCES raw.orders(order_id),
    category        text,             -- delivery | payment | product | refund | other
    priority        text,
    opened_ts       timestamptz NOT NULL,
    resolved_ts     timestamptz,
    text            text,
    loaded_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON raw.support_tickets (customer_id);
CREATE INDEX ON raw.support_tickets (opened_ts);
CREATE INDEX ON raw.support_tickets (category);

COMMENT ON SCHEMA raw IS
  'Operational source data. Olist core + simulated web_events, campaigns, releases, support_tickets. Agents may NOT query raw.* directly — use kpi.* views.';
