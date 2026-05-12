"""Admin routes — wraps the Anthropic Admin API for the dashboard.

The admin key stays server-side; the dashboard authenticates with its
normal X-API-Key and the backend forwards using ANTHROPIC_ADMIN_API_KEY.
503 when the admin key isn't configured so the UI can hide the page.
"""

from __future__ import annotations

from typing import Annotated, Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from biq import anthropic_admin
from biq.anthropic_admin import AdminKeyMissingError, KeyStatus, UpdatableStatus

router = APIRouter(prefix="/admin", tags=["admin"])


def _map_admin_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AdminKeyMissingError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        body: Any
        try:
            body = exc.response.json()
        except Exception:
            body = exc.response.text[:500]
        return HTTPException(
            status_code=exc.response.status_code,
            detail={"upstream": body, "endpoint": str(exc.request.url)},
        )
    if isinstance(exc, httpx.HTTPError):
        return HTTPException(status_code=502, detail=f"upstream error: {exc}")
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/anthropic-keys")
def list_anthropic_keys(
    status: Annotated[KeyStatus | None, Query()] = None,
    workspace_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    after_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """List all API keys on the org (admin-key gated)."""
    try:
        return anthropic_admin.list_api_keys(
            status=status,
            workspace_id=workspace_id,
            limit=limit,
            after_id=after_id,
        )
    except Exception as exc:
        raise _map_admin_error(exc) from exc


@router.get("/anthropic-keys/{api_key_id}")
def get_anthropic_key(api_key_id: str) -> dict[str, Any]:
    """Get a single API key by id."""
    try:
        return anthropic_admin.get_api_key(api_key_id)
    except Exception as exc:
        raise _map_admin_error(exc) from exc


class UpdateAnthropicKeyRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    status: UpdatableStatus | None = None


@router.post("/anthropic-keys/{api_key_id}")
def update_anthropic_key(
    api_key_id: str,
    payload: UpdateAnthropicKeyRequest,
) -> dict[str, Any]:
    """Rename or change status (active/inactive/archived).

    Setting `status="archived"` is the revoke path — the key stops working
    immediately. There is no un-archive; create a fresh key in the Console
    if you need a working one again.
    """
    if payload.name is None and payload.status is None:
        raise HTTPException(
            status_code=422,
            detail="provide at least one of name, status",
        )
    try:
        return anthropic_admin.update_api_key(
            api_key_id,
            name=payload.name,
            status=payload.status,
        )
    except Exception as exc:
        raise _map_admin_error(exc) from exc
