"""Wrapper around the Anthropic Admin API.

Reaches the org-level routes under https://api.anthropic.com/v1/organizations/*.
Auth is a separate **admin** key (`ANTHROPIC_ADMIN_API_KEY`) issued in the
Claude Console — NOT the regular `sk-ant-...` model-call key. The admin key
must never leave the backend.

Surface today: just API-key listing + retrieval. The wrapper is intentionally
thin — no caching, no auth retry — so the FastAPI handler can decide on TTLs
and error mapping.
"""

from __future__ import annotations

from typing import Any, Literal

import httpx

from biq.config import settings

_BASE = "https://api.anthropic.com/v1/organizations"
_API_VERSION = "2023-06-01"
_TIMEOUT_S = 20.0

KeyStatus = Literal["active", "inactive", "archived", "expired"]


class AdminKeyMissingError(RuntimeError):
    """Raised when ANTHROPIC_ADMIN_API_KEY is not configured."""


def _client() -> httpx.Client:
    if not settings.anthropic_admin_api_key:
        raise AdminKeyMissingError("ANTHROPIC_ADMIN_API_KEY not set — Admin API calls disabled.")
    return httpx.Client(
        base_url=_BASE,
        timeout=_TIMEOUT_S,
        headers={
            "anthropic-version": _API_VERSION,
            "X-Api-Key": settings.anthropic_admin_api_key,
        },
    )


def list_api_keys(
    *,
    status: KeyStatus | None = None,
    workspace_id: str | None = None,
    created_by_user_id: str | None = None,
    limit: int = 100,
    after_id: str | None = None,
    before_id: str | None = None,
) -> dict[str, Any]:
    """GET /v1/organizations/api_keys.

    Returns the raw paginated envelope:
        {"data": [APIKey, ...], "first_id", "last_id", "has_more"}
    """
    params: dict[str, str | int] = {"limit": limit}
    if status is not None:
        params["status"] = status
    if workspace_id is not None:
        params["workspace_id"] = workspace_id
    if created_by_user_id is not None:
        params["created_by_user_id"] = created_by_user_id
    if after_id is not None:
        params["after_id"] = after_id
    if before_id is not None:
        params["before_id"] = before_id

    with _client() as client:
        resp = client.get("/api_keys", params=params)
        resp.raise_for_status()
        return resp.json()


def get_api_key(api_key_id: str) -> dict[str, Any]:
    """GET /v1/organizations/api_keys/{api_key_id}."""
    with _client() as client:
        resp = client.get(f"/api_keys/{api_key_id}")
        resp.raise_for_status()
        return resp.json()


# Status values the upstream update endpoint accepts. Note that "expired"
# is a read-only state — you can transition to inactive/archived but not
# back to expired.
UpdatableStatus = Literal["active", "inactive", "archived"]


def update_api_key(
    api_key_id: str,
    *,
    name: str | None = None,
    status: UpdatableStatus | None = None,
) -> dict[str, Any]:
    """POST /v1/organizations/api_keys/{api_key_id}.

    Pass `name` to rename, `status` to (de)activate or archive. Setting
    `status="archived"` is the way to revoke a leaked key — it can no
    longer be used to call the API. At least one of name/status must be
    given; an empty body is rejected here before the network hop.
    """
    if name is None and status is None:
        raise ValueError("update_api_key requires at least one of name, status")

    body: dict[str, Any] = {}
    if name is not None:
        body["name"] = name
    if status is not None:
        body["status"] = status

    with _client() as client:
        resp = client.post(f"/api_keys/{api_key_id}", json=body)
        resp.raise_for_status()
        return resp.json()
