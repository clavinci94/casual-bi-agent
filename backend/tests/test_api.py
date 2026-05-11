"""HTTP API tests via FastAPI TestClient.

Doesn't spin up a real ASGI server — TestClient calls handlers in-process,
so the same DB connection + audit module is used. R-service-bound endpoints
will return an error payload in the body when r-causal is down (instead of
HTTP 5xx); tests assert the shape, not the value, of those.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from biq.api.app import app
from biq.audit import run_context

client = TestClient(app)


# ---- Health ------------------------------------------------------------


def test_healthz() -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_readyz_reports_db_status(db_ready: bool) -> None:
    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "ok"
    assert "r_service" in body  # may be ok or error depending on local state


def test_root_redirect_info() -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["docs"] == "/docs"


# ---- KPIs --------------------------------------------------------------


def test_list_kpis() -> None:
    r = client.get("/api/kpis")
    assert r.status_code == 200
    assert "conversion_rate_daily" in r.json()["views"]


def test_kpi_query_unknown_view(db_ready: bool) -> None:
    r = client.get("/api/kpis/not_a_view?start=2018-01-01&end=2018-02-01")
    assert r.status_code == 400
    assert "not allowed" in r.json()["detail"]


def test_kpi_query_real(db_ready: bool) -> None:
    r = client.get(
        "/api/kpis/conversion_rate_daily",
        params={
            "start": "2018-04-15",
            "end": "2018-05-10",
            "group_by": ["device"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["row_count"] > 0
    devices = {row["device"] for row in body["rows"]}
    assert {"mobile", "desktop", "tablet"} <= devices


# ---- Recommendations + decisions ---------------------------------------


def test_list_recommendations_all(db_ready: bool) -> None:
    r = client.get("/api/recommendations?status=all&limit=10")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_recommendation_404() -> None:
    r = client.get("/api/recommendations/does-not-exist")
    assert r.status_code == 404


def test_decision_404() -> None:
    r = client.post(
        "/api/recommendations/does-not-exist/decision",
        json={"decision": "approve", "approver": "test"},
    )
    assert r.status_code == 404


def test_decision_approves_real_recommendation(db_ready: bool) -> None:
    # Create a recommendation we own so we can approve it
    from biq.audit import log_recommendation

    with run_context(trigger="test", prompt="api decision test") as ctx:
        rec_id = log_recommendation(
            run_id=ctx.run_id,
            title="api test",
            body="test body for mobile",
            confidence=0.5,
            action_type="read_only",
            risk_level="low",
        )

    r = client.post(
        f"/api/recommendations/{rec_id}/decision",
        json={"decision": "approve", "approver": "pytest"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"

    # Verify audit row exists
    from biq.db import engine

    with engine.connect() as conn:
        d = conn.execute(
            text("SELECT decision, approver FROM audit.hitl_decisions WHERE rec_id = :id"),
            {"id": rec_id},
        ).one()
    assert d[0] == "approve"
    assert d[1] == "pytest"


# ---- Runs --------------------------------------------------------------


def test_list_runs(db_ready: bool) -> None:
    r = client.get("/api/runs?limit=5")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_run_404() -> None:
    r = client.get("/api/runs/no-such-run-id")
    assert r.status_code == 404


def test_get_run_detail(db_ready: bool) -> None:
    # Create a fresh run to fetch
    from biq.audit import log_step

    with run_context(trigger="test", prompt="api run detail test") as ctx:
        log_step(ctx, "tester", "noop", input={"k": "v"})
        rid = ctx.run_id

    r = client.get(f"/api/runs/{rid}")
    assert r.status_code == 200
    body = r.json()
    assert body["run"]["run_id"] == rid
    assert len(body["steps"]) >= 1
    assert body["steps"][0]["agent_name"] == "tester"


# ---- Investigations ----------------------------------------------------


def test_anomaly_investigation(db_ready: bool) -> None:
    r = client.post(
        "/api/investigations/anomaly",
        json={"reference_date": "2018-05-05"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "insights" in body
    assert "run_id" in body
