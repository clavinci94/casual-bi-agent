"""Liveness + readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from biq import __version__
from biq.db import engine
from biq.tools import causal as causal_tools

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness — process is up. Should not hit DB."""
    return {"status": "ok", "version": __version__}


@router.get("/readyz")
def readyz() -> dict[str, str]:
    """Readiness — DB reachable, optional R service status."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"

    r_payload = causal_tools.health()
    r_status = "ok" if r_payload.get("status") == "ok" else "error"

    overall = "ok" if db_status == "ok" else "error"

    return {
        "status": overall,
        "db": db_status,
        "r_service": r_status,
        "version": __version__,
    }
