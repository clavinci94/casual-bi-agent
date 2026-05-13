"""User-facing system settings — runtime feature toggles persisted in
audit.system_config. Keep this list short: complex configuration belongs
in .env / docs / ADRs, not in a UI toggle. Useful when a non-engineer
needs to pause a cost-incurring background job without redeploying.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from biq import system_config

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


class SystemSettingsPatch(BaseModel):
    """Partial update — every field optional so the client can change one
    toggle without round-tripping the whole document."""

    briefing_daily_active: bool | None = None


def _read() -> SystemSettings:
    return SystemSettings(
        briefing_daily_active=system_config.briefing_daily_active(),
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

    return _read()
