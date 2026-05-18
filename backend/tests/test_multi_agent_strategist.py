"""Tests for the Strategist-Lead and OptionGenerator sub-worker.

No live LLM is hit by default — a stub Anthropic client is passed in so the
Pydantic-validation and escalation paths are exercised hermetically.
A @pytest.mark.live test goes against real Claude when ANTHROPIC_API_KEY
is set; it is opt-in via `pytest -m live`.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from biq.agents.multi.leads.strategist import (
    SIGNIFICANT_P_VALUE,
    SIGNIFICANT_REL_EFFECT,
    _escalate_if_needed,
    _has_high_impact_finding,
    strategist_node,
)
from biq.agents.multi.state import (
    AnalysisResult,
    CausalEstimate,
    Finding,
)
from biq.agents.multi.sub import option_generator

# --- Helpers -------------------------------------------------------------


def _stub_client(tool_input: dict, *, stop_reason: str = "tool_use"):
    """Build a fake Anthropic client returning one tool_use block."""

    block = SimpleNamespace(type="tool_use", name="submit_strategy", input=tool_input)
    resp = SimpleNamespace(content=[block], stop_reason=stop_reason)
    messages = SimpleNamespace(create=lambda **kwargs: resp)
    return SimpleNamespace(messages=messages)


def _stub_client_no_tool_use():
    """LLM returned text instead of calling the tool — the unhappy path."""
    block = SimpleNamespace(type="text", text="Sorry, no idea.")
    resp = SimpleNamespace(content=[block], stop_reason="end_turn")
    messages = SimpleNamespace(create=lambda **kwargs: resp)
    return SimpleNamespace(messages=messages)


VALID_TOOL_PAYLOAD = {
    "options": [
        {
            "title": "Rollback Mobile-Release v2",
            "body_de": "Letztes Release zurücknehmen und Hotfix vorbereiten.",
            "expected_impact_de": "Conversion sollte sich innerhalb 24h erholen.",
            "risks_de": ["Marketing-Kampagne läuft auf neue UI"],
            "effort": "medium",
        },
        {
            "title": "A/B-Test Checkout-Variante",
            "body_de": "Alte Checkout-UI gegen neue testen.",
            "expected_impact_de": "Klärt ob neue UI Ursache ist.",
            "risks_de": ["Verzögert finale Entscheidung um eine Woche"],
            "effort": "low",
        },
    ],
    "risk_level": "medium",
}


# --- Escalation unit tests ----------------------------------------------


def test_high_impact_finding_detected() -> None:
    big = CausalEstimate(method="m", treatment="t", outcome="o", estimate=-0.4, p_value=0.001)
    small = CausalEstimate(method="m", treatment="t", outcome="o", estimate=-0.05, p_value=0.001)
    assert _has_high_impact_finding([big]) is True
    assert _has_high_impact_finding([small]) is False
    assert _has_high_impact_finding([]) is False


def test_high_impact_requires_significance() -> None:
    big_but_insignificant = CausalEstimate(
        method="m", treatment="t", outcome="o", estimate=-0.4, p_value=0.3
    )
    assert _has_high_impact_finding([big_but_insignificant]) is False


def test_escalation_lifts_risk_to_high() -> None:
    assert _escalate_if_needed("medium", has_high_impact=True) == "high"
    assert _escalate_if_needed("low", has_high_impact=True) == "high"
    assert _escalate_if_needed("low", has_high_impact=False) == "low"
    assert _escalate_if_needed("high", has_high_impact=False) == "high"


def test_thresholds_are_documented() -> None:
    """Guard against accidental loosening of the escalation thresholds."""
    assert SIGNIFICANT_REL_EFFECT == 0.25
    assert SIGNIFICANT_P_VALUE == 0.05


# --- Sub-worker (option_generator) tests --------------------------------


def test_option_generator_returns_parsed_options_with_stub_client() -> None:
    analysis = AnalysisResult(
        findings=[Finding(title="X", body_de="Y", confidence=0.8, severity="high")],
        causal_estimates=[
            CausalEstimate(method="m", treatment="t", outcome="o", estimate=-0.5, p_value=0.01)
        ],
    )
    result = option_generator.run(
        analysis=analysis,
        question="Was tun?",
        client=_stub_client(VALID_TOOL_PAYLOAD),
    )
    assert not result.skipped
    assert len(result.options) == 2
    assert result.options[0].title.startswith("Rollback")
    assert result.options[0].effort == "medium"
    assert result.risk_level == "medium"


def test_option_generator_handles_tool_use_missing() -> None:
    analysis = AnalysisResult(
        findings=[Finding(title="X", body_de="Y", confidence=0.8, severity="high")],
    )
    result = option_generator.run(analysis=analysis, client=_stub_client_no_tool_use())
    assert result.skipped
    assert "did not call submit_strategy" in (result.notes or "")


def test_option_generator_handles_invalid_payload() -> None:
    bad = {"options": [{"title": "no body or impact"}], "risk_level": "medium"}
    analysis = AnalysisResult(
        findings=[Finding(title="X", body_de="Y", confidence=0.8, severity="high")],
    )
    result = option_generator.run(analysis=analysis, client=_stub_client(bad))
    assert result.skipped
    assert "Pydantic" in (result.notes or "")


# --- Strategist-Lead tests ----------------------------------------------


def test_strategist_skips_without_analysis() -> None:
    patch = strategist_node({"question": "foo"})
    assert patch["strategy"].options == []
    assert "no analysis" in (patch["strategy"].notes or "")
    assert patch["completed"] == ["strategy"]


def test_strategist_escalates_risk_for_high_impact_estimate(monkeypatch) -> None:
    """Even if the LLM proposes 'medium', a big causal effect forces 'high'."""
    analysis = AnalysisResult(
        findings=[Finding(title="X", body_de="Y", confidence=0.9, severity="high")],
        causal_estimates=[
            CausalEstimate(
                method="CausalImpact",
                treatment="release v2",
                outcome="conversion (mobile)",
                estimate=-0.49,
                p_value=0.001,
            )
        ],
    )
    # Patch the sub-worker so the strategist sees a deterministic LLM response.
    monkeypatch.setattr(
        option_generator,
        "run",
        lambda **kw: option_generator.OptionSubResult(
            options=[],
            risk_level="medium",
            notes="stub",
        ),
    )
    patch = strategist_node({"question": "Was tun?", "analysis": analysis})
    assert patch["strategy"].risk_level == "high"
    assert "escalated" in (patch["strategy"].notes or "")


# --- Live (real Claude) — opt-in ----------------------------------------


@pytest.mark.live
def test_option_generator_against_real_claude() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    analysis = AnalysisResult(
        findings=[
            Finding(
                title="Conversion eingebrochen auf mobile: -51%",
                body_de="Mobile-Conversion fiel von 4.1% auf 2.0%.",
                confidence=0.95,
                severity="high",
            )
        ],
        causal_estimates=[
            CausalEstimate(
                method="CausalImpact",
                treatment="Window 2018-04-15..05-10",
                outcome="conversion (mobile)",
                estimate=-0.49,
                p_value=0.001,
                notes="controls=[desktop, tablet]",
            )
        ],
    )
    result = option_generator.run(analysis=analysis, question="Warum eingebrochen?")
    assert not result.skipped, result.notes
    assert 1 <= len(result.options) <= 4
    for opt in result.options:
        assert opt.title
        assert opt.body_de
        assert opt.risks_de
