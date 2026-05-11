-- Schema: audit
-- Full observability of every agent run, every tool call, every recommendation.
-- This is product, not afterthought: trust = traceability.
-- Outcomes flow back into kg.* as Decision and Outcome nodes.

CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE audit.agent_runs (
    run_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         text,
    trigger         text NOT NULL,            -- user_prompt | schedule | webhook | retry
    prompt          text,
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    status          text NOT NULL DEFAULT 'running',  -- running | ok | error | aborted
    cost_usd        numeric(10,4),
    llm_tokens_in   int,
    llm_tokens_out  int,
    error_message   text
);
CREATE INDEX ON audit.agent_runs (started_at);
CREATE INDEX ON audit.agent_runs (status);

CREATE TABLE audit.agent_steps (
    step_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          uuid NOT NULL REFERENCES audit.agent_runs(run_id) ON DELETE CASCADE,
    seq             int  NOT NULL,
    agent_name      text NOT NULL,            -- orchestrator | data | stats | causal | narrative | review
    action          text NOT NULL,
    input           jsonb,
    output          jsonb,
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    latency_ms      int,
    UNIQUE (run_id, seq)
);
CREATE INDEX ON audit.agent_steps (run_id);

CREATE TABLE audit.tool_calls (
    call_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    step_id         uuid NOT NULL REFERENCES audit.agent_steps(step_id) ON DELETE CASCADE,
    tool_name       text NOT NULL,            -- sql | kg | python | r | n8n | docs
    tool_version    text,
    params          jsonb NOT NULL,
    result_summary  jsonb,
    rows_returned   int,
    cached          boolean NOT NULL DEFAULT false,
    latency_ms      int,
    error           text,
    called_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON audit.tool_calls (step_id);
CREATE INDEX ON audit.tool_calls (tool_name);

CREATE TABLE audit.sources_used (
    use_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          uuid NOT NULL REFERENCES audit.agent_runs(run_id) ON DELETE CASCADE,
    source_kind     text NOT NULL,            -- kpi_view | doc | kg_query | external_api
    source_ref      text NOT NULL,
    rows_or_chunks  int,
    freshness_ts    timestamptz                -- when source data was last updated
);
CREATE INDEX ON audit.sources_used (run_id);

CREATE TABLE audit.recommendations (
    rec_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          uuid NOT NULL REFERENCES audit.agent_runs(run_id) ON DELETE CASCADE,
    title           text NOT NULL,
    body            text NOT NULL,
    confidence      numeric,                  -- 0..1
    action_type     text NOT NULL,            -- read_only | draft_email | adjust_forecast | open_ticket | ...
    risk_level      text NOT NULL,            -- low | medium | high
    status          text NOT NULL DEFAULT 'pending',  -- pending | approved | rejected | expired
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON audit.recommendations (status);
CREATE INDEX ON audit.recommendations (run_id);

CREATE TABLE audit.hitl_decisions (
    decision_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rec_id          uuid NOT NULL REFERENCES audit.recommendations(rec_id) ON DELETE CASCADE,
    approver        text NOT NULL,
    decision        text NOT NULL,            -- approve | reject | modify
    comment         text,
    decided_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit.outcomes (
    outcome_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rec_id              uuid NOT NULL REFERENCES audit.recommendations(rec_id) ON DELETE CASCADE,
    metric              text NOT NULL,
    expected_effect     numeric,
    observed_effect     numeric,
    observation_start   timestamptz NOT NULL,
    observation_end     timestamptz NOT NULL,
    measured_at         timestamptz NOT NULL DEFAULT now(),
    notes               text
);

COMMENT ON SCHEMA audit IS
  'Full traceability. Every agent run, every tool call, every recommendation, every HITL approval, every measured outcome. Outcomes flow back into kg.* as Decision and Outcome nodes — closes the learning loop.';
