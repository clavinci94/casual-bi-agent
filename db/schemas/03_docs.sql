-- Schema: docs
-- Unstructured knowledge + vector index for Agentic RAG.
-- Sources: Markdown notes, support ticket texts, review comments,
--          campaign briefs, external news.

CREATE SCHEMA IF NOT EXISTS docs;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE docs.documents (
    doc_id          text PRIMARY KEY DEFAULT gen_random_uuid()::text,
    title           text NOT NULL,
    source          text NOT NULL,        -- markdown | support_ticket | review | campaign_brief | external
    source_ref      text,                 -- e.g. ticket_id, review_id, file path
    kind            text NOT NULL,        -- note | postmortem | brief | external_news
    text            text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    -- explicit expiry — agents must downweight or skip after this
    valid_until     timestamptz,
    author          text,
    tags            text[]
);
CREATE INDEX ON docs.documents (source);
CREATE INDEX ON docs.documents (created_at);
CREATE INDEX ON docs.documents USING GIN (tags);

CREATE TABLE docs.chunks (
    chunk_id        text PRIMARY KEY DEFAULT gen_random_uuid()::text,
    doc_id          text NOT NULL REFERENCES docs.documents(doc_id) ON DELETE CASCADE,
    position        int  NOT NULL,
    text            text NOT NULL,
    -- 1536 = OpenAI text-embedding-3-small; swap if model changes
    embedding       vector(1536),
    entities        text[],               -- extracted entity names
    kpis_mentioned  text[],               -- extracted KPI references
    UNIQUE (doc_id, position)
);
CREATE INDEX ON docs.chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX ON docs.chunks USING GIN (entities);
CREATE INDEX ON docs.chunks USING GIN (kpis_mentioned);

COMMENT ON SCHEMA docs IS
  'Unstructured documents + embeddings. Qualitative context for Agentic RAG. Always check documents.valid_until before treating a chunk as current.';
