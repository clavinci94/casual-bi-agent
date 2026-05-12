"""external signals cache

Cache for results from external-intelligence tools (Tavily web search,
news, Google Trends, market data). The agent and the Markt-Radar page
both read through this table so identical queries within the TTL window
don't re-bill the upstream API.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-12
"""

from __future__ import annotations

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS raw.external_signals (
            signal_id   text        PRIMARY KEY DEFAULT gen_random_uuid()::text,
            source      text        NOT NULL,                          -- 'tavily' | 'news' | 'trends' | 'market'
            query_key   text        NOT NULL,                          -- normalised query string
            payload     jsonb       NOT NULL,                          -- whatever the upstream returned
            fetched_at  timestamptz NOT NULL DEFAULT now(),
            expires_at  timestamptz NOT NULL
        );
        CREATE INDEX IF NOT EXISTS external_signals_lookup_idx
            ON raw.external_signals (source, query_key, expires_at DESC);
        CREATE INDEX IF NOT EXISTS external_signals_recent_idx
            ON raw.external_signals (source, fetched_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS raw.external_signals CASCADE")
