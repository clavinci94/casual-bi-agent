"""Unit tests for biq.agents.investigator.

The Anthropic client is mocked — these tests exercise the loop logic
(plan extraction, budget enforcement, result envelope) without burning
real tokens or requiring an API key. The full end-to-end investigation
is exercised manually via `make investigate`.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from biq.agents import investigator as inv

# --- Helpers ------------------------------------------------------------


def _make_block(type_: str, **fields: object) -> SimpleNamespace:
    """Mimic an Anthropic response content block (.type + attributes + model_dump)."""
    ns = SimpleNamespace(type=type_, **fields)
    ns.model_dump = lambda: {"type": type_, **fields}  # type: ignore[method-assign]
    return ns


def _make_response(
    content: list[SimpleNamespace],
    stop_reason: str,
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_read: int = 0,
    cache_write: int = 0,
) -> SimpleNamespace:
    usage = SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_write,
    )
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=usage)


# --- _result envelope ---------------------------------------------------


def test_result_success_envelope() -> None:
    out = inv._result(
        "run-1",
        final_answer="Mobile checkout regressed -38%.",
        recommendation_ids=["rec-1"],
        iterations=3,
        plan="Probe conversion -> compare desktop -> CausalImpact",
        tokens=(1000, 500, 8000, 200),
    )
    assert out["run_id"] == "run-1"
    assert out["final_answer"].startswith("Mobile")
    assert out["recommendation_ids"] == ["rec-1"]
    assert out["iterations"] == 3
    assert out["plan"].startswith("Probe")
    assert out["tokens"] == {
        "input": 1000,
        "output": 500,
        "cache_read": 8000,
        "cache_write": 200,
    }
    assert "error" not in out


def test_result_error_envelope_omits_final_answer() -> None:
    out = inv._result(
        "run-2",
        error="budget exceeded",
        stop_reason="tool_use",
        recommendation_ids=[],
        iterations=10,
        plan=None,
        tokens=(0, 0, 0, 0),
    )
    assert out["error"] == "budget exceeded"
    assert out["stop_reason"] == "tool_use"
    assert "final_answer" not in out
    assert "plan" not in out  # plan=None should be omitted


# --- investigate() with mocked Anthropic --------------------------------


@pytest.fixture
def patched_anthropic(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch the Anthropic class so `client.messages.create` is a MagicMock
    the test can configure with .return_value or .side_effect."""
    monkeypatch.setattr(inv.settings, "anthropic_api_key", "test-key", raising=False)
    create_mock = MagicMock()
    fake_client = MagicMock()
    fake_client.messages.create = create_mock
    fake_factory = MagicMock(return_value=fake_client)
    monkeypatch.setattr(inv, "Anthropic", fake_factory)
    return create_mock


def test_extracts_plan_from_thinking_and_returns_final(
    patched_anthropic: MagicMock, db_ready: bool
) -> None:
    """Happy path: thinking block on turn 1 captured as plan; end_turn returns final_answer."""
    plan_thoughts = (
        "1. Probe conversion_rate_daily by device\n"
        "2. Compare to desktop baseline\n"
        "3. If gap >10%, run CausalImpact on the mobile_v2 release window"
    )
    patched_anthropic.return_value = _make_response(
        [
            _make_block("thinking", thinking=plan_thoughts),
            _make_block("text", text="No anomaly found in the requested window."),
        ],
        stop_reason="end_turn",
    )

    out = inv.investigate("Anything weird in the last 7 days?", max_iterations=3)

    assert "error" not in out
    assert out["final_answer"].startswith("No anomaly")
    assert out["plan"] == plan_thoughts
    assert out["iterations"] == 1
    assert out["tokens"]["input"] == 100
    # Verify thinking was actually requested on the API call
    call_kwargs = patched_anthropic.call_args.kwargs
    assert call_kwargs["thinking"] == {
        "type": "enabled",
        "budget_tokens": inv.DEFAULT_THINKING_BUDGET,
    }


def test_input_budget_stops_loop(patched_anthropic: MagicMock, db_ready: bool) -> None:
    """When cumulative input tokens exceed the cap, the loop halts with an error envelope."""
    # First response: tool_use that consumes more input than the budget allows.
    patched_anthropic.side_effect = [
        _make_response(
            [
                _make_block("thinking", thinking="plan"),
                _make_block(
                    "tool_use",
                    id="tu_1",
                    name="kpi_query",
                    input={
                        "view": "conversion_rate_daily",
                        "start": "2018-04-01",
                        "end": "2018-05-01",
                    },
                ),
            ],
            stop_reason="tool_use",
            input_tokens=600,
        ),
    ]

    # Stub the tool dispatcher so we don't hit the real DB.
    with patch.object(inv, "_dispatch", return_value={"row_count": 0, "rows": []}):
        out = inv.investigate("budget test", max_iterations=5, max_input_tokens=500)

    assert "error" in out
    assert "input token budget exceeded" in out["error"]
    assert out["iterations"] == 1
    assert out["recommendation_ids"] == []


def test_output_budget_stops_loop(patched_anthropic: MagicMock, db_ready: bool) -> None:
    patched_anthropic.side_effect = [
        _make_response(
            [
                _make_block("thinking", thinking="plan"),
                _make_block(
                    "tool_use",
                    id="tu_2",
                    name="kpi_query",
                    input={
                        "view": "conversion_rate_daily",
                        "start": "2018-04-01",
                        "end": "2018-05-01",
                    },
                ),
            ],
            stop_reason="tool_use",
            output_tokens=999_999,
        ),
    ]

    with patch.object(inv, "_dispatch", return_value={"row_count": 0, "rows": []}):
        out = inv.investigate("output budget test", max_iterations=5, max_output_tokens=1000)

    assert "error" in out
    assert "output token budget exceeded" in out["error"]
