"""HTTP layer for /api/settings — GET reads the live system_config,
PUT updates one or many toggles and round-trips the audit actor through
request.state.user. Auth runs in 'disabled' mode so we don't need a JWT
for these tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from biq.api.app import app
    from biq.config import settings

    monkeypatch.setattr(settings, "biq_auth_mode", "disabled")
    return TestClient(app)


def test_get_settings_returns_current_state(
    monkeypatch: pytest.MonkeyPatch, db_ready: bool
) -> None:
    c = _client(monkeypatch)
    r = c.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    # The three known toggles are always present, regardless of DB state.
    assert "briefing_daily_active" in body
    assert "data_source" in body
    assert "briefing_model" in body
    assert body["data_source"] in ("sim", "live")
    assert body["briefing_model"] in ("haiku", "sonnet", "opus")


def test_put_settings_updates_briefing_model(
    monkeypatch: pytest.MonkeyPatch, db_ready: bool
) -> None:
    from biq import system_config

    c = _client(monkeypatch)
    try:
        r = c.put("/api/settings", json={"briefing_model": "haiku"})
        assert r.status_code == 200
        assert r.json()["briefing_model"] == "haiku"
        # And persisted server-side.
        assert system_config.briefing_model_tier() == "haiku"
    finally:
        system_config.set_briefing_model_tier("sonnet")


def test_put_settings_rejects_invalid_briefing_model(
    monkeypatch: pytest.MonkeyPatch, db_ready: bool
) -> None:
    c = _client(monkeypatch)
    r = c.put("/api/settings", json={"briefing_model": "gpt-5"})
    # Pydantic Literal validation surfaces as 422.
    assert r.status_code == 422


def test_put_settings_rejects_invalid_data_source(
    monkeypatch: pytest.MonkeyPatch, db_ready: bool
) -> None:
    c = _client(monkeypatch)
    r = c.put("/api/settings", json={"data_source": "production"})
    assert r.status_code == 400
    assert "sim" in r.json()["detail"]


def test_put_settings_toggles_briefing_daily(
    monkeypatch: pytest.MonkeyPatch, db_ready: bool
) -> None:
    from biq import system_config

    c = _client(monkeypatch)
    try:
        r = c.put("/api/settings", json={"briefing_daily_active": False})
        assert r.status_code == 200
        assert r.json()["briefing_daily_active"] is False
    finally:
        system_config.set_briefing_daily_active(True)
