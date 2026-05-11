"""API-key auth behaviour: open when unset, gated when configured."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _client_with_api_key(monkeypatch: pytest.MonkeyPatch, key: str | None) -> TestClient:
    """Build a fresh TestClient with biq_api_key set on the shared settings.

    We mutate the live settings object rather than re-importing modules because
    the api routers were already wired into the FastAPI app at import time.
    """
    from biq.api.app import app
    from biq.config import settings

    monkeypatch.setattr(settings, "biq_api_key", key)
    return TestClient(app)


def test_api_open_when_key_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client_with_api_key(monkeypatch, None)
    r = c.get("/api/kpis")
    assert r.status_code == 200


def test_api_rejects_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client_with_api_key(monkeypatch, "secret-123")
    r = c.get("/api/kpis")
    assert r.status_code == 401
    assert "X-API-Key" in r.json()["detail"]


def test_api_rejects_wrong_key(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client_with_api_key(monkeypatch, "secret-123")
    r = c.get("/api/kpis", headers={"X-API-Key": "nope"})
    assert r.status_code == 401


def test_api_accepts_correct_key(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client_with_api_key(monkeypatch, "secret-123")
    r = c.get("/api/kpis", headers={"X-API-Key": "secret-123"})
    assert r.status_code == 200


def test_health_never_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Health endpoints stay open for liveness probes regardless of key."""
    c = _client_with_api_key(monkeypatch, "secret-123")
    assert c.get("/healthz").status_code == 200
