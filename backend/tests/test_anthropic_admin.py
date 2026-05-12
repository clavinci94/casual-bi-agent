"""Anthropic Admin API wrapper + /api/admin/* routes.

httpx is mocked via a MockTransport — these are pure unit tests; no real
upstream calls and no admin key needed except the env-toggle the wrapper
checks.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from biq import anthropic_admin
from biq.api.app import app

client = TestClient(app)


def _fake_transport(handler) -> httpx.MockTransport:  # type: ignore[no-untyped-def]
    return httpx.MockTransport(handler)


@pytest.fixture
def admin_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        anthropic_admin.settings,
        "anthropic_admin_api_key",
        "sk-ant-admin-test",
        raising=False,
    )


def test_wrapper_raises_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        anthropic_admin.settings,
        "anthropic_admin_api_key",
        None,
        raising=False,
    )
    with pytest.raises(anthropic_admin.AdminKeyMissingError):
        anthropic_admin.list_api_keys()


def test_wrapper_sends_correct_headers_and_parses_response(
    admin_key_set: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "apikey_01abc",
                        "type": "api_key",
                        "name": "biq-prod",
                        "status": "active",
                        "partial_key_hint": "sk-ant-...xyz",
                        "created_at": "2026-04-01T00:00:00Z",
                        "created_by": {"id": "user_1", "type": "user"},
                        "expires_at": None,
                        "workspace_id": None,
                    }
                ],
                "first_id": "apikey_01abc",
                "last_id": "apikey_01abc",
                "has_more": False,
            },
        )

    # Patch _client to inject the mock transport without changing the wrapper.
    orig_client = anthropic_admin._client

    def fake_client() -> httpx.Client:
        real = orig_client()
        real._transport = _fake_transport(handler)
        return real

    monkeypatch.setattr(anthropic_admin, "_client", fake_client)

    payload = anthropic_admin.list_api_keys(status="active", limit=50)

    assert payload["data"][0]["id"] == "apikey_01abc"
    assert captured["url"].startswith("https://api.anthropic.com/v1/organizations/api_keys")
    assert "status=active" in captured["url"]
    assert "limit=50" in captured["url"]
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["headers"]["x-api-key"] == "sk-ant-admin-test"


def test_get_api_key_hits_id_path(
    admin_key_set: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "id": "apikey_01abc",
                "type": "api_key",
                "name": "biq-prod",
                "status": "active",
                "partial_key_hint": "sk-ant-...xyz",
                "created_at": "2026-04-01T00:00:00Z",
                "created_by": {"id": "user_1", "type": "user"},
                "expires_at": None,
                "workspace_id": None,
            },
        )

    orig_client = anthropic_admin._client

    def fake_client() -> httpx.Client:
        c = orig_client()
        c._transport = _fake_transport(handler)
        return c

    monkeypatch.setattr(anthropic_admin, "_client", fake_client)

    out = anthropic_admin.get_api_key("apikey_01abc")
    assert out["id"] == "apikey_01abc"
    assert seen["url"].endswith("/api_keys/apikey_01abc")


# ---- Route tests --------------------------------------------------------


def test_route_503_when_admin_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        anthropic_admin.settings,
        "anthropic_admin_api_key",
        None,
        raising=False,
    )
    r = client.get("/api/admin/anthropic-keys")
    assert r.status_code == 503
    assert "ANTHROPIC_ADMIN_API_KEY" in r.json()["detail"]


def test_route_returns_payload(
    admin_key_set: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "apikey_01abc",
                        "type": "api_key",
                        "name": "biq-dev",
                        "status": "active",
                        "partial_key_hint": "sk-ant-...xyz",
                        "created_at": "2026-04-01T00:00:00Z",
                        "created_by": {"id": "user_1", "type": "user"},
                        "expires_at": None,
                        "workspace_id": None,
                    }
                ],
                "first_id": "apikey_01abc",
                "last_id": "apikey_01abc",
                "has_more": False,
            },
        )

    orig_client = anthropic_admin._client

    def fake_client() -> httpx.Client:
        c = orig_client()
        c._transport = _fake_transport(handler)
        return c

    monkeypatch.setattr(anthropic_admin, "_client", fake_client)

    r = client.get("/api/admin/anthropic-keys?status=active")
    assert r.status_code == 200
    body = r.json()
    assert body["data"][0]["name"] == "biq-dev"


def test_route_maps_upstream_404(
    admin_key_set: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not_found"})

    orig_client = anthropic_admin._client

    def fake_client() -> httpx.Client:
        c = orig_client()
        c._transport = _fake_transport(handler)
        return c

    monkeypatch.setattr(anthropic_admin, "_client", fake_client)

    r = client.get("/api/admin/anthropic-keys/apikey_unknown")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["upstream"] == {"error": "not_found"}
