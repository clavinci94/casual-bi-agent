"""Alembic environment.

Migrations are raw SQL (we don't use SQLAlchemy ORM models), so
target_metadata stays None and autogenerate is not used. Each revision
either calls `op.execute(...)` with a SQL string or reads from
`db/schemas/*.sql`.

Connection URL comes from biq.config.settings (loads .env + env vars).
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from biq.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

# No ORM models — raw SQL migrations only.
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
