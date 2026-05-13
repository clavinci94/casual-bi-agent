"""Tiny runtime-config layer backed by audit.system_config.

For settings the manager toggles from the UI (cost gates, feature flags)
that should:
- persist across backend restarts
- be auditable (updated_by + updated_at)
- be cheap to read on every request (single-row select on a small table)

Not for app config (env-vars, secrets) — those still live in `.env` /
`biq.config.settings`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text

from biq.db import engine

_logger = logging.getLogger(__name__)


def get(key: str, default: Any = None) -> Any:
    """Return the JSONB value stored under `key`, or `default` if missing.

    The store is small — no in-process cache needed. Postgres handles the
    row-lookup in microseconds.
    """
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT value FROM audit.system_config WHERE key = :k"),
                {"k": key},
            ).first()
        if row is None:
            return default
        return row[0]
    except Exception as exc:
        _logger.warning("system_config get(%s) failed: %s", key, exc)
        return default


def set_(key: str, value: Any, *, updated_by: str | None = None) -> None:
    """Upsert a JSONB value under `key`. Idempotent."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit.system_config (key, value, updated_by) "
                "VALUES (:k, cast(:v as jsonb), :by) "
                "ON CONFLICT (key) DO UPDATE SET "
                "  value = EXCLUDED.value, "
                "  updated_at = now(), "
                "  updated_by = EXCLUDED.updated_by"
            ),
            {"k": key, "v": json.dumps(value, default=str), "by": updated_by},
        )


# ---- Convenience helpers for known keys ------------------------------


def briefing_daily_active() -> bool:
    """True if the daily Tagesbriefing should run; False to pause cost-
    incurring Sonnet synthesis. Default True (matches migration default)."""
    payload = get("briefing.daily_active", {"active": True})
    if isinstance(payload, dict):
        return bool(payload.get("active", True))
    return True


def set_briefing_daily_active(active: bool, *, updated_by: str | None = None) -> None:
    set_("briefing.daily_active", {"active": bool(active)}, updated_by=updated_by)
