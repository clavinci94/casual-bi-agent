"""Tagesbriefing routes — read today's briefing or trigger a refresh.

GET  /api/briefing/today    — returns today's briefing (cached if exists,
                              generates one on first call of the day)
POST /api/briefing/refresh  — always generates a fresh briefing. Used by
                              the daily cron (n8n) so the user-facing
                              GET path stays fast.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from biq import system_config
from biq.agents.briefing import generate_briefing, get_today_briefing

router = APIRouter(prefix="/briefing", tags=["briefing"])


_DEACTIVATED_PAYLOAD: dict[str, Any] = {
    "run_id": None,
    "generated_at": None,
    "briefing": {
        "headline": "Tagesbriefing pausiert — zum Aktivieren in den Einstellungen wieder einschalten.",
        "signals": [],
    },
    "from_cache": False,
    "deactivated": True,
}


@router.get("/today")
def today() -> dict[str, Any]:
    """Return today's briefing.

    When the manager has paused the daily briefing in /settings the API
    returns a deactivated stub immediately — even if a cached briefing
    from before the pause still exists. That keeps the UI consistent
    with the toggle state. Reactivating reveals the cached briefing
    again on the next call.

    Otherwise: cache hit (if exists) or generate on the fly. The first
    user of the day pays the ~20 s latency; everyone after gets the
    cached copy instantly.

    Returns 503 if the Anthropic key is missing and we'd need to call
    the model to satisfy the request.
    """
    if not system_config.briefing_daily_active():
        return _DEACTIVATED_PAYLOAD

    cached = get_today_briefing()
    if cached is not None:
        return cached
    try:
        return generate_briefing(force_refresh=False, model=system_config.briefing_model())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/refresh")
def refresh() -> dict[str, Any]:
    """Force-generate a fresh briefing, ignoring any cache for today.

    Cron workflows call this. The model tier is read from system_config
    so /settings can dial cost down to Haiku (~10× cheaper) without a
    redeploy.
    """
    try:
        return generate_briefing(force_refresh=True, model=system_config.briefing_model())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
