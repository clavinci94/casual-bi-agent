"""SQLAlchemy engine + session factory.

Every checked-out connection runs `SET LOCAL biq.data_source = '<value>'`
based on settings.biq_data_source so the kpi.shopify_* views (which
filter on `current_setting('biq.data_source', true)`) see the right
slice without callers needing to remember.

`SET LOCAL` would be transaction-scoped, but we use `SET` (session-
scoped) so views work outside an explicit transaction too — Postgres
clears it when the connection is returned to the pool, so there is no
cross-request leakage on a fresh checkout.
"""

from __future__ import annotations

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from biq.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)


@event.listens_for(engine, "connect")
def _set_session_vars(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
    """Apply Causal-BI session-level Postgres vars on every fresh connection.

    We read the current data_source from audit.system_config using the
    *same* DBAPI connection that's being initialised — going through the
    SQLAlchemy engine would recurse into this listener and deadlock.

    Important: we MUST issue the SET outside an explicit transaction —
    SQLAlchemy / psycopg wraps cursor.execute in an implicit txn, and a
    plain `SET` inside a txn behaves like `SET LOCAL` (reverts on commit).
    Flipping the DBAPI to autocommit for the duration makes the value
    stick at session level for the lifetime of the connection.
    """
    prev_autocommit = dbapi_connection.autocommit
    dbapi_connection.autocommit = True
    try:
        cur = dbapi_connection.cursor()
        try:
            # Read the current data_source value directly with this cursor.
            # Falls back to the env-var default if the table or row is
            # missing (e.g. before migration 0005 has been applied).
            value: str | None = None
            try:
                cur.execute(
                    "SELECT value->>'value' FROM audit.system_config WHERE key='biq.data_source'"
                )
                row = cur.fetchone()
                if row and row[0] in ("sim", "live"):
                    value = row[0]
            except Exception:
                pass
            if value is None:
                env_val = (settings.biq_data_source or "sim").lower()
                value = env_val if env_val in ("sim", "live") else "sim"

            cur.execute(f"SET SESSION biq.data_source = '{value}'")
        finally:
            cur.close()
    finally:
        dbapi_connection.autocommit = prev_autocommit


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


def current_data_source() -> str:
    """Return the live `biq.data_source` value the next query will see.
    Useful for the topbar indicator and for debugging."""
    with engine.connect() as conn:
        return (
            conn.execute(text("SELECT current_setting('biq.data_source', true)")).scalar() or "sim"
        )
