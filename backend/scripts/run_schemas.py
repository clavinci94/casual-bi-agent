"""Apply all SQL schema files to the configured database.

Usage:
    uv run python scripts/run_schemas.py
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from biq.db import engine

SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "db" / "schemas"


def main() -> None:
    files = sorted(SCHEMA_DIR.glob("*.sql"))
    if not files:
        raise SystemExit(f"No SQL files found in {SCHEMA_DIR}")

    with engine.begin() as conn:
        for f in files:
            print(f"Applying {f.name} ...")
            conn.execute(text(f.read_text()))
    print("Done.")


if __name__ == "__main__":
    main()
