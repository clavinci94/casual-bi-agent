"""Round-trip tests for the audit.system_config layer.

Verifies that the typed helpers (briefing_daily_active, data_source,
briefing_model_tier) read and write the JSONB store correctly, fall back
to safe defaults when the row is missing, and reject invalid values.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from biq import system_config
from biq.db import engine


def _wipe_key(key: str) -> None:
    """Force a clean slate so default-fallback paths are exercised."""
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM audit.system_config WHERE key = :k"),
            {"k": key},
        )


# ---------------------------------------------------------------------------
# generic get / set_
# ---------------------------------------------------------------------------


def test_get_returns_default_when_key_missing(db_ready: bool) -> None:
    fake_key = f"test.missing.{uuid.uuid4()}"
    assert system_config.get(fake_key, default="fallback") == "fallback"


def test_set_then_get_roundtrips_a_dict(db_ready: bool) -> None:
    fake_key = f"test.roundtrip.{uuid.uuid4()}"
    try:
        system_config.set_(fake_key, {"hello": "world", "n": 7}, updated_by="pytest")
        assert system_config.get(fake_key) == {"hello": "world", "n": 7}
    finally:
        _wipe_key(fake_key)


def test_set_overwrites_previous_value(db_ready: bool) -> None:
    fake_key = f"test.overwrite.{uuid.uuid4()}"
    try:
        system_config.set_(fake_key, {"v": 1})
        system_config.set_(fake_key, {"v": 2})
        assert system_config.get(fake_key) == {"v": 2}
    finally:
        _wipe_key(fake_key)


# ---------------------------------------------------------------------------
# briefing_daily_active
# ---------------------------------------------------------------------------


def test_briefing_daily_active_defaults_true_when_unset(db_ready: bool) -> None:
    _wipe_key("briefing.daily_active")
    assert system_config.briefing_daily_active() is True


def test_set_briefing_daily_active_toggles_off_and_back(db_ready: bool) -> None:
    try:
        system_config.set_briefing_daily_active(False, updated_by="pytest")
        assert system_config.briefing_daily_active() is False
        system_config.set_briefing_daily_active(True, updated_by="pytest")
        assert system_config.briefing_daily_active() is True
    finally:
        _wipe_key("briefing.daily_active")


# ---------------------------------------------------------------------------
# data_source
# ---------------------------------------------------------------------------


def test_data_source_falls_back_to_env_when_unset(db_ready: bool) -> None:
    _wipe_key("biq.data_source")
    # whatever the env says, the helper must return a valid token
    assert system_config.data_source() in ("sim", "live")


def test_set_data_source_persists_choice(db_ready: bool) -> None:
    try:
        system_config.set_data_source("live", updated_by="pytest")
        assert system_config.data_source() == "live"
        system_config.set_data_source("sim", updated_by="pytest")
        assert system_config.data_source() == "sim"
    finally:
        _wipe_key("biq.data_source")


def test_set_data_source_rejects_invalid_value(db_ready: bool) -> None:
    with pytest.raises(ValueError):
        system_config.set_data_source("production")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# briefing_model_tier
# ---------------------------------------------------------------------------


def test_briefing_model_tier_defaults_to_sonnet(db_ready: bool) -> None:
    _wipe_key("briefing.model")
    assert system_config.briefing_model_tier() == "sonnet"
    assert system_config.briefing_model() == "claude-sonnet-4-6"


def test_set_briefing_model_tier_resolves_to_full_model_id(db_ready: bool) -> None:
    try:
        system_config.set_briefing_model_tier("haiku", updated_by="pytest")
        assert system_config.briefing_model_tier() == "haiku"
        assert system_config.briefing_model() == "claude-haiku-4-5"

        system_config.set_briefing_model_tier("opus", updated_by="pytest")
        assert system_config.briefing_model_tier() == "opus"
        assert system_config.briefing_model() == "claude-opus-4-7"
    finally:
        _wipe_key("briefing.model")


def test_set_briefing_model_tier_rejects_unknown(db_ready: bool) -> None:
    with pytest.raises(ValueError):
        system_config.set_briefing_model_tier("gpt-5")
