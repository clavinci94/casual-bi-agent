"""User-facing system settings — runtime feature toggles persisted in
audit.system_config. Keep this list short: complex configuration belongs
in .env / docs / ADRs, not in a UI toggle. Useful when a non-engineer
needs to pause a cost-incurring background job without redeploying.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from biq import system_config
from biq.db import current_data_source

BriefingModelTier = Literal["haiku", "sonnet", "opus"]

router = APIRouter(prefix="/settings", tags=["settings"])


class SystemSettings(BaseModel):
    """Manager-visible toggles. Add a field here + a row in
    audit.system_config + a `set_*` helper to expose a new toggle.
    """

    briefing_daily_active: bool = Field(
        default=True,
        description=(
            "When True, the daily Tagesbriefing runs every weekday at 07:00. "
            "When False, n8n's cron still fires but the API returns a "
            "deactivated stub without calling Anthropic — saves ~CHF 0.10/day."
        ),
    )
    data_source: str = Field(
        default="sim",
        description=(
            "Which slice of raw.shopify_* the dashboard reads. 'sim' for the "
            "simulated demo store, 'live' for the real Shopify dev-store. "
            "Read-only via the UI — changed by editing BIQ_DATA_SOURCE in "
            ".env and restarting the backend."
        ),
    )
    briefing_model: BriefingModelTier = Field(
        default="sonnet",
        description=(
            "Anthropic model tier used by the daily briefing agent. 'haiku' "
            "is cheapest (~10x less than Sonnet), 'sonnet' is the default "
            "quality-cost balance, 'opus' is highest-quality for thorough "
            "summaries. Switch on the fly when running costs need cutting."
        ),
    )


class SystemSettingsPatch(BaseModel):
    """Partial update — every field optional so the client can change one
    toggle without round-tripping the whole document."""

    briefing_daily_active: bool | None = None
    data_source: str | None = None
    briefing_model: BriefingModelTier | None = None


def _read() -> SystemSettings:
    return SystemSettings(
        briefing_daily_active=system_config.briefing_daily_active(),
        data_source=current_data_source(),
        briefing_model=system_config.briefing_model_tier(),  # type: ignore[arg-type]
    )


@router.get("", response_model=SystemSettings)
def read_settings() -> SystemSettings:
    return _read()


@router.put("", response_model=SystemSettings)
def update_settings(
    patch: SystemSettingsPatch,
    request: Request,
) -> SystemSettings:
    # The Bearer-JWT auth path stashes verified claims on request.state.user
    # so audit trail captures who flipped the toggle. Falls back to
    # "manager:ui" when running in api_key / disabled auth mode.
    actor = "manager:ui"
    user = getattr(request.state, "user", None)
    if isinstance(user, dict):
        actor = f"sso:{user.get('email') or user.get('sub') or 'unknown'}"

    if patch.briefing_daily_active is not None:
        system_config.set_briefing_daily_active(
            patch.briefing_daily_active,
            updated_by=actor,
        )

    if patch.data_source is not None:
        if patch.data_source not in ("sim", "live"):
            raise HTTPException(
                status_code=400,
                detail=f"data_source must be 'sim' or 'live', got {patch.data_source!r}",
            )
        system_config.set_data_source(patch.data_source, updated_by=actor)
        # Existing pool connections have the previous SET still cached at
        # the Postgres session level. Dispose flushes them; next checkout
        # opens a fresh physical connection and the connect-event runs
        # SET with the new value.
        from biq.db import engine

        engine.dispose()

    if patch.briefing_model is not None:
        try:
            system_config.set_briefing_model_tier(patch.briefing_model, updated_by=actor)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _read()
