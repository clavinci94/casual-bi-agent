-- Schema: kg
-- Knowledge Graph: entities, decisions, outcomes, learned causal links.
-- Uses Apache AGE if available on Neon; otherwise the relational fallback below.
-- See docs/decisions/ADR-001-kg-store.md once written.

CREATE SCHEMA IF NOT EXISTS kg;

-- =================================================================
-- Branch A: Apache AGE (preferred, enable once verified on Neon)
-- =================================================================
-- CREATE EXTENSION IF NOT EXISTS age;
-- LOAD 'age';
-- SET search_path = ag_catalog, "$user", public;
-- SELECT create_graph('causalbi');
--
-- Node labels:
--   Customer · Product · Category · Region · Segment · Campaign ·
--   Release · KPI · Insight · Hypothesis · Evidence · Decision · Outcome
--
-- Edge labels:
--   BOUGHT · BELONGS_TO · INFLUENCED · SUPPORTS · BACKS ·
--   LED_TO · RESULTED_IN · MEASURES

-- =================================================================
-- Branch B: relational fallback (works on any Postgres)
-- =================================================================

CREATE TABLE kg.nodes (
    node_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    label           text NOT NULL,            -- Customer | Product | Insight | Decision | Outcome | ...
    external_ref    text,                     -- link back to raw.* id where applicable
    properties      jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (label, external_ref)
);
CREATE INDEX ON kg.nodes (label);
CREATE INDEX ON kg.nodes USING GIN (properties);

CREATE TABLE kg.edges (
    edge_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    from_node       uuid NOT NULL REFERENCES kg.nodes(node_id) ON DELETE CASCADE,
    to_node         uuid NOT NULL REFERENCES kg.nodes(node_id) ON DELETE CASCADE,
    label           text NOT NULL,            -- BOUGHT | INFLUENCED | LED_TO | RESULTED_IN | ...
    properties      jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- causal properties when relevant
    effect_size     numeric,                  -- e.g. -0.08 = -8%
    ci_lower        numeric,
    ci_upper        numeric,
    method          text,                     -- causal_impact | did | matching | observation
    confidence      numeric,                  -- 0..1
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON kg.edges (from_node, label);
CREATE INDEX ON kg.edges (to_node, label);
CREATE INDEX ON kg.edges (label);

COMMENT ON SCHEMA kg IS
  'Knowledge graph of entities, decisions, outcomes and learned causal effects. The organisational memory: every Decision is linked to the Evidence that supported it and the Outcome it produced.';
