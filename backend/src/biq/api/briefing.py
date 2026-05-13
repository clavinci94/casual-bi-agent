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

from biq.agents.briefing import generate_briefing, get_today_briefing

router = APIRouter(prefix="/briefing", tags=["briefing"])


@router.get("/today")
def today() -> dict[str, Any]:
    """Return today's briefing.

    If a cached briefing for the current day already exists in
    audit.agent_runs, return it. Otherwise generate one synchronously.
    The first user of the day pays the ~20 s latency; everyone after
    that gets the cached copy instantly.

    Returns 503 if the Anthropic key is missing and we'd need to call
    the model to satisfy the request.
    """
    cached = get_today_briefing()
    if cached is not None:
        return cached
    try:
        return generate_briefing(force_refresh=False)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/refresh")
def refresh() -> dict[str, Any]:
    """Force-generate a fresh briefing, ignoring any cache for today.

    Cron workflows call this. Cost is one Sonnet call (~CHF 0.10-0.15)
    plus all six signal fetches.
    """
    try:
        return generate_briefing(force_refresh=True)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
