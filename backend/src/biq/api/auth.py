"""Pluggable authentication for /api/*.

Three modes, switched by BIQ_AUTH_MODE in .env:

  api_key      — X-API-Key header == BIQ_API_KEY (current default)
  bearer_jwt   — Authorization: Bearer <jwt>, validated via JWKS
  disabled     — no auth at all (local dev only)

The bearer_jwt path is the SSO scaffolding. Auth0, Azure AD, Okta,
Keycloak — anything with a standard OIDC discovery endpoint works.
JWKS keys are cached in-memory with a short TTL so we don't hit the
IdP on every request.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from biq.config import settings

_logger = logging.getLogger(__name__)

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
_BEARER = HTTPBearer(auto_error=False)


# --- API-key path (legacy / machine-to-machine) -----------------------


def _require_api_key(api_key: str | None) -> None:
    expected = settings.biq_api_key
    if not expected:
        return
    if api_key != expected:
        raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")


# --- Bearer-JWT path (SSO) --------------------------------------------

_JWKS_CACHE: dict[str, Any] = {"keys": None, "fetched_at": 0.0}
_JWKS_TTL_SECONDS = 3600.0


def _load_jwks() -> dict[str, Any]:
    """Return a cached JWKS document; refresh after TTL."""
    import time

    import httpx

    now = time.time()
    if _JWKS_CACHE["keys"] is not None and (now - _JWKS_CACHE["fetched_at"]) < _JWKS_TTL_SECONDS:
        return _JWKS_CACHE["keys"]

    url = settings.biq_jwt_jwks_url
    if not url:
        raise HTTPException(
            status_code=500,
            detail="BIQ_AUTH_MODE=bearer_jwt requires BIQ_JWT_JWKS_URL",
        )
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url)
        resp.raise_for_status()
        keys = resp.json()
    _JWKS_CACHE["keys"] = keys
    _JWKS_CACHE["fetched_at"] = now
    return keys


def _require_bearer(token: str | None) -> dict[str, Any]:
    if not token:
        raise HTTPException(status_code=401, detail="missing Bearer token")
    try:
        import jwt
        from jwt import PyJWKClient
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="pyjwt[crypto] not installed — `uv add 'pyjwt[crypto]'`",
        ) from exc

    if not settings.biq_jwt_jwks_url:
        raise HTTPException(
            status_code=500,
            detail="BIQ_AUTH_MODE=bearer_jwt requires BIQ_JWT_JWKS_URL",
        )

    jwks_client = PyJWKClient(settings.biq_jwt_jwks_url, cache_keys=True, lifespan=3600)
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=["RS256", "ES256"],
            audience=settings.biq_jwt_audience,
            issuer=settings.biq_jwt_issuer,
            options={"require": ["exp", "iss"]},
        )
        return claims
    except jwt.PyJWTError as exc:
        _logger.warning("JWT validation failed: %s", exc)
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc


# --- The dependency the router uses -----------------------------------


def require_api_key(
    request: Request,
    api_key: Annotated[str | None, Security(_API_KEY_HEADER)] = None,
    bearer: Annotated[HTTPAuthorizationCredentials | None, Security(_BEARER)] = None,
) -> None:
    """FastAPI dependency. Picks the auth mode from settings and enforces
    accordingly. Name kept as `require_api_key` for back-compat with
    existing router wiring.
    """
    mode = (settings.biq_auth_mode or "api_key").lower()
    if mode == "disabled":
        return
    if mode == "bearer_jwt":
        # Bearer is the primary path. Fall back to X-API-Key for
        # machine callers (n8n cron, scripts, smoke tests) — same
        # shared secret as in api_key mode, just lets the Auth0 flow
        # remain user-facing without locking out automation.
        if bearer is not None:
            claims = _require_bearer(bearer.credentials)
            request.state.user = claims
            return
        if api_key is not None:
            _require_api_key(api_key)
            request.state.user = {"sub": "service:api-key"}
            return
        raise HTTPException(status_code=401, detail="missing Bearer or X-API-Key")
    # default: api_key
    _require_api_key(api_key)
