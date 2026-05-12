"""Apply all DB schemas via Alembic (production path) or by directly
executing the SQL files (bootstrap for empty databases).

The Makefile target `db-schemas` calls this. Equivalent to running:
    cd backend && uv run alembic upgrade head

Usage:
    uv run python scripts/run_schemas.py
    uv run python scripts/run_schemas.py --stamp      # mark current state
                                                       # as latest without
                                                       # running migrations
"""

from __future__ import annotations

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stamp",
        action="store_true",
        help="Stamp the DB as 'head' without running migrations.",
    )
    args = parser.parse_args()

    ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = Config(str(ini))

    if args.stamp:
        print("Stamping DB at head (no schema changes applied)...")
        command.stamp(cfg, "head")
    else:
        print("Running alembic upgrade head...")
        command.upgrade(cfg, "head")
    print("Done.")


if __name__ == "__main__":
    main()
