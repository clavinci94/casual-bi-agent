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


def data_source() -> str:
    """Current data slice for kpi.shopify_* views: 'sim' or 'live'.

    Reads audit.system_config first (manager toggle from /settings),
    falls back to the BIQ_DATA_SOURCE env-var, then 'sim' as the
    safe default. Stored as `{"value": "sim"}` for forward-compat.
    """
    payload = get("biq.data_source", None)
    if isinstance(payload, dict):
        v = payload.get("value")
        if v in ("sim", "live"):
            return v
    # No row yet — first-time install. Use env var if present.
    from biq.config import settings as _s

    env_val = (_s.biq_data_source or "sim").lower()
    return env_val if env_val in ("sim", "live") else "sim"


def set_data_source(value: str, *, updated_by: str | None = None) -> None:
    if value not in ("sim", "live"):
        raise ValueError(f"data_source must be 'sim' or 'live', got {value!r}")
    set_("biq.data_source", {"value": value}, updated_by=updated_by)
