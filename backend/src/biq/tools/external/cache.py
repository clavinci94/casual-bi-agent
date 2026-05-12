"""Cache helper for external-intelligence tools.

The pattern:

    payload = cached_query(
        source="tavily",
        query_key="conversion drop ecommerce mai 2018",
        ttl_minutes=60,
        fetch=lambda: _call_tavily(...),
    )

`cached_query` looks up `raw.external_signals` for a non-expired row
matching (source, query_key). On a hit it returns the cached payload.
On a miss it calls `fetch()`, stores the result with the requested TTL,
and returns it. Cache failures (DB down, etc.) never block the agent —
the live fetch is always attempted as a fallback.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text

from biq.db import engine

_logger = logging.getLogger(__name__)


def _normalise(query_key: str) -> str:
    """Hash long / awkward keys so the index stays compact."""
    if len(query_key) <= 200:
        return query_key.lower()
    return hashlib.sha256(query_key.lower().encode()).hexdigest()


def get_cached(source: str, query_key: str) -> dict[str, Any] | None:
    """Return the cached payload if a non-expired entry exists, else None."""
    norm = _normalise(query_key)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT payload FROM raw.external_signals "
                    "WHERE source = :source AND query_key = :key "
                    "  AND expires_at > now() "
                    "ORDER BY fetched_at DESC LIMIT 1"
                ),
                {"source": source, "key": norm},
            ).first()
        if row is None:
            return None
        payload = row[0]
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        _logger.warning("external cache read failed: %s", exc)
        return None


def store_cached(
    source: str,
    query_key: str,
    payload: dict[str, Any],
    ttl_minutes: int,
) -> None:
    """Persist a fetched payload. Best-effort — DB errors don't propagate."""
    norm = _normalise(query_key)
    expires = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO raw.external_signals "
                    "(source, query_key, payload, expires_at) "
                    "VALUES (:source, :key, cast(:payload as jsonb), :exp)"
                ),
                {
                    "source": source,
                    "key": norm,
                    "payload": json.dumps(payload, default=str),
                    "exp": expires,
                },
            )
    except Exception as exc:
        _logger.warning("external cache write failed: %s", exc)


def cached_query(
    source: str,
    query_key: str,
    ttl_minutes: int,
    fetch: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Read-through cache. See module docstring."""
    hit = get_cached(source, query_key)
    if hit is not None:
        return {**hit, "cache": "hit"}
    payload = fetch()
    # Only cache successful payloads — avoids pinning an error message
    # in front of a later working call.
    if "error" not in payload:
        store_cached(source, query_key, payload, ttl_minutes)
    return {**payload, "cache": "miss"}
