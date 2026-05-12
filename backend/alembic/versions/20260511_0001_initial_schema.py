"""initial schema (raw, kpi, docs, kg, audit)

Wraps db/schemas/*.sql in a single revision so production deploys use
`alembic upgrade head` as the source of truth. The numbered SQL files
remain as the authoritative DDL — this migration just executes them.

For existing databases (where run_schemas.py was used), run
`alembic stamp head` once to mark this revision as applied without
re-running it.

Revision ID: 0001
Revises:
Create Date: 2026-05-11
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

# alembic/versions/<this>.py  →  parents[3] is the repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_DIR = _REPO_ROOT / "db" / "schemas"

_FILES = (
    "01_raw.sql",
    "02_kpi.sql",
    "03_docs.sql",
    "04_kg.sql",
    "05_audit.sql",
)


def upgrade() -> None:
    for filename in _FILES:
        sql = (_SCHEMA_DIR / filename).read_text()
        op.execute(sql)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS audit CASCADE")
    op.execute("DROP SCHEMA IF EXISTS kg CASCADE")
    op.execute("DROP SCHEMA IF EXISTS docs CASCADE")
    op.execute("DROP SCHEMA IF EXISTS kpi CASCADE")
    op.execute("DROP SCHEMA IF EXISTS raw CASCADE")
