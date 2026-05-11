"""API-key authentication.

When `BIQ_API_KEY` is set in the environment, requests to /api/* must
include `X-API-Key: <value>`. When unset (dev mode), auth is bypassed so
local development and tests don't need an extra step.

This is the minimum that lets us deploy to Render with public URLs without
exposing the agent loop to the open internet. Swap for OAuth/SSO when a
real auth provider is in scope.
"""

from __future__ import annotations

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from biq.config import settings

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: str | None = Security(_API_KEY_HEADER)) -> None:
    """FastAPI dependency: enforce X-API-Key when BIQ_API_KEY is configured."""
    expected = settings.biq_api_key
    if not expected:
        return  # auth disabled
    if api_key != expected:
        raise HTTPException(
            status_code=401,
            detail="missing or invalid X-API-Key",
        )
