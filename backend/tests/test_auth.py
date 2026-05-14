"""Auth behaviour for the three BIQ_AUTH_MODE values:
- disabled    → no auth, anyone reaches /api/*
- api_key     → X-API-Key gates everything
- bearer_jwt  → Auth0 access-tokens are the primary path, X-API-Key is
                the machine-caller fallback so n8n/scripts keep working
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _client_with_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: str = "api_key",
    api_key: str | None = None,
    jwks_url: str | None = None,
    issuer: str | None = None,
    audience: str | None = None,
) -> TestClient:
    """Spin up a TestClient with the auth settings of our choosing.

    The app + routers are already imported, so we mutate the live
    settings object rather than reload everything.
    """
    from biq.api.app import app
    from biq.config import settings

    monkeypatch.setattr(settings, "biq_auth_mode", mode)
    monkeypatch.setattr(settings, "biq_api_key", api_key)
    monkeypatch.setattr(settings, "biq_jwt_jwks_url", jwks_url)
    monkeypatch.setattr(settings, "biq_jwt_issuer", issuer)
    monkeypatch.setattr(settings, "biq_jwt_audience", audience)
    return TestClient(app)


def _make_rsa_keypair() -> tuple[Any, dict[str, Any]]:
    """Return (private_key, jwks_dict) — JWKS with one RSA public key
    in the shape Auth0 / PyJWKClient expects."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = key.public_key().public_numbers()

    def _b64url(n: int) -> str:
        import base64

        b = n.to_bytes((n.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": "test-kid",
                "use": "sig",
                "alg": "RS256",
                "n": _b64url(public_numbers.n),
                "e": _b64url(public_numbers.e),
            }
        ]
    }
    return key, jwks


def _sign_jwt(
    private_key: Any,
    *,
    issuer: str,
    audience: str,
    exp_offset_seconds: int = 300,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = _dt.datetime.now(_dt.timezone.utc)
    payload: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": "auth0|test-user",
        "iat": int(now.timestamp()),
        "exp": int((now + _dt.timedelta(seconds=exp_offset_seconds)).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return jwt.encode(payload, pem, algorithm="RS256", headers={"kid": "test-kid"})


# ---------------------------------------------------------------------------
# api_key mode
# ---------------------------------------------------------------------------


def test_api_key_open_when_key_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client_with_settings(monkeypatch, mode="api_key", api_key=None)
    assert c.get("/api/kpis").status_code == 200


def test_api_key_rejects_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client_with_settings(monkeypatch, mode="api_key", api_key="secret-123")
    r = c.get("/api/kpis")
    assert r.status_code == 401
    assert "X-API-Key" in r.json()["detail"]


def test_api_key_rejects_wrong(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client_with_settings(monkeypatch, mode="api_key", api_key="secret-123")
    assert c.get("/api/kpis", headers={"X-API-Key": "nope"}).status_code == 401


def test_api_key_accepts_correct(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client_with_settings(monkeypatch, mode="api_key", api_key="secret-123")
    assert c.get("/api/kpis", headers={"X-API-Key": "secret-123"}).status_code == 200


def test_health_never_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client_with_settings(monkeypatch, mode="api_key", api_key="secret-123")
    assert c.get("/healthz").status_code == 200


# ---------------------------------------------------------------------------
# disabled mode
# ---------------------------------------------------------------------------


def test_disabled_mode_lets_everyone_through(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client_with_settings(monkeypatch, mode="disabled")
    assert c.get("/api/kpis").status_code == 200


# ---------------------------------------------------------------------------
# bearer_jwt mode
# ---------------------------------------------------------------------------


ISSUER = "https://test-tenant.eu.auth0.com/"
AUDIENCE = "https://api.causal-bi.local"
JWKS_URL = "https://test-tenant.eu.auth0.com/.well-known/jwks.json"


@pytest.fixture
def rsa_jwks() -> tuple[Any, dict[str, Any]]:
    return _make_rsa_keypair()


@pytest.fixture
def patched_jwks(rsa_jwks: tuple[Any, dict[str, Any]]):
    """Patch PyJWKClient.fetch_data so it returns our in-memory JWKS
    instead of hitting Auth0 over the network."""
    _, jwks = rsa_jwks
    with patch(
        "jwt.PyJWKClient.fetch_data",
        return_value=jwks,
    ):
        yield


def test_bearer_rejects_request_without_any_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = _client_with_settings(
        monkeypatch,
        mode="bearer_jwt",
        api_key="machine-secret",
        jwks_url=JWKS_URL,
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    r = c.get("/api/kpis")
    assert r.status_code == 401
    assert "Bearer" in r.json()["detail"] or "X-API-Key" in r.json()["detail"]


def test_bearer_accepts_valid_jwt(
    monkeypatch: pytest.MonkeyPatch,
    rsa_jwks: tuple[Any, dict[str, Any]],
    patched_jwks: None,
) -> None:
    private_key, _ = rsa_jwks
    token = _sign_jwt(private_key, issuer=ISSUER, audience=AUDIENCE)
    c = _client_with_settings(
        monkeypatch,
        mode="bearer_jwt",
        api_key="machine-secret",
        jwks_url=JWKS_URL,
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    r = c.get("/api/kpis", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_bearer_rejects_expired_jwt(
    monkeypatch: pytest.MonkeyPatch,
    rsa_jwks: tuple[Any, dict[str, Any]],
    patched_jwks: None,
) -> None:
    private_key, _ = rsa_jwks
    token = _sign_jwt(private_key, issuer=ISSUER, audience=AUDIENCE, exp_offset_seconds=-60)
    c = _client_with_settings(
        monkeypatch,
        mode="bearer_jwt",
        jwks_url=JWKS_URL,
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    r = c.get("/api/kpis", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert "invalid token" in r.json()["detail"]


def test_bearer_rejects_wrong_audience(
    monkeypatch: pytest.MonkeyPatch,
    rsa_jwks: tuple[Any, dict[str, Any]],
    patched_jwks: None,
) -> None:
    private_key, _ = rsa_jwks
    token = _sign_jwt(private_key, issuer=ISSUER, audience="https://wrong-audience.example")
    c = _client_with_settings(
        monkeypatch,
        mode="bearer_jwt",
        jwks_url=JWKS_URL,
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    r = c.get("/api/kpis", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_bearer_rejects_wrong_issuer(
    monkeypatch: pytest.MonkeyPatch,
    rsa_jwks: tuple[Any, dict[str, Any]],
    patched_jwks: None,
) -> None:
    private_key, _ = rsa_jwks
    token = _sign_jwt(private_key, issuer="https://attacker.example/", audience=AUDIENCE)
    c = _client_with_settings(
        monkeypatch,
        mode="bearer_jwt",
        jwks_url=JWKS_URL,
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    r = c.get("/api/kpis", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_bearer_mode_falls_back_to_api_key_for_machines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In bearer_jwt mode, n8n/scripts that send X-API-Key still get in.
    Without this fallback, every cron job would need a user-session JWT."""
    c = _client_with_settings(
        monkeypatch,
        mode="bearer_jwt",
        api_key="machine-secret",
        jwks_url=JWKS_URL,
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    r = c.get("/api/kpis", headers={"X-API-Key": "machine-secret"})
    assert r.status_code == 200


def test_bearer_mode_rejects_wrong_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = _client_with_settings(
        monkeypatch,
        mode="bearer_jwt",
        api_key="machine-secret",
        jwks_url=JWKS_URL,
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    r = c.get("/api/kpis", headers={"X-API-Key": "nope"})
    assert r.status_code == 401


def test_bearer_mode_500_when_jwks_url_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Misconfiguration (bearer_jwt without JWKS URL) surfaces as a clear
    server error, not a silent bypass."""
    c = _client_with_settings(
        monkeypatch,
        mode="bearer_jwt",
        jwks_url=None,
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    # Empty Bearer triggers the "missing token" 401 before we ever look
    # at JWKS_URL — supply a non-empty (but unverifiable) one to force
    # the JWKS lookup path.
    r = c.get("/api/kpis", headers={"Authorization": "Bearer placeholder"})
    assert r.status_code == 500
    assert "BIQ_JWT_JWKS_URL" in r.json()["detail"]


def test_health_open_in_bearer_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client_with_settings(
        monkeypatch,
        mode="bearer_jwt",
        jwks_url=JWKS_URL,
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    assert c.get("/healthz").status_code == 200


# Quiet the unused-import warning — `json` is used inside string fixtures.
_ = json
