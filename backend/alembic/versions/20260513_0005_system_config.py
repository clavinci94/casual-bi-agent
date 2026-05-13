"""system config key-value store

A tiny audit.system_config table that holds runtime feature flags / toggles
the manager can flip from /settings without restarting anything. First
use-case: enable/disable the daily Tagesbriefing so Anthropic credits
aren't burned during quiet periods.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-13
"""

from __future__ import annotations

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit.system_config (
            key         text        PRIMARY KEY,
            value       jsonb       NOT NULL,
            updated_at  timestamptz NOT NULL DEFAULT now(),
            updated_by  text                                            -- free-text actor label
        );

        -- Default: briefing is active. Setting to {"active": false} disables
        -- the daily synthesis and surfaces a friendly message in the UI.
        INSERT INTO audit.system_config (key, value, updated_by)
        VALUES ('briefing.daily_active', '{"active": true}'::jsonb, 'migration:0005')
        ON CONFLICT (key) DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit.system_config;")
