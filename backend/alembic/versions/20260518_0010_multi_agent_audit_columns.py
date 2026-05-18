"""extend audit.agent_steps for hierarchical multi-agent traces

The single-agent and deterministic LangGraph paths log one row per step
with just `seq` for ordering. The multi-agent investigator (supervisor →
leads → sub-workers) needs per-step parent attribution, agent level, and
LLM cost accounting so that a single investigation can be replayed as a
tree, billed per tenant, and compared in evals.

All columns are nullable so the existing single-agent path continues to
work unchanged.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-18
"""

from __future__ import annotations

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE audit.agent_steps
            ADD COLUMN IF NOT EXISTS parent_step_id text
                REFERENCES audit.agent_steps(step_id) ON DELETE CASCADE,
            ADD COLUMN IF NOT EXISTS agent_level    text,
            ADD COLUMN IF NOT EXISTS model          text,
            ADD COLUMN IF NOT EXISTS tokens_in      int,
            ADD COLUMN IF NOT EXISTS tokens_out     int,
            ADD COLUMN IF NOT EXISTS cost_usd       numeric(10,4);
    """)

    # Tree traversal goes parent → children; index the FK.
    op.execute(
        "CREATE INDEX IF NOT EXISTS agent_steps_parent_idx "
        "ON audit.agent_steps (parent_step_id);"
    )

    # Enforce the allowed level vocabulary at the DB layer so a typo in
    # application code surfaces immediately rather than as a silent join miss.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'agent_steps_level_check'
            ) THEN
                ALTER TABLE audit.agent_steps
                    ADD CONSTRAINT agent_steps_level_check
                    CHECK (agent_level IS NULL OR agent_level IN ('supervisor','lead','sub'));
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE audit.agent_steps DROP CONSTRAINT IF EXISTS agent_steps_level_check;"
    )
    op.execute("DROP INDEX IF EXISTS audit.agent_steps_parent_idx;")
    op.execute("""
        ALTER TABLE audit.agent_steps
            DROP COLUMN IF EXISTS cost_usd,
            DROP COLUMN IF EXISTS tokens_out,
            DROP COLUMN IF EXISTS tokens_in,
            DROP COLUMN IF EXISTS model,
            DROP COLUMN IF EXISTS agent_level,
            DROP COLUMN IF EXISTS parent_step_id;
    """)
