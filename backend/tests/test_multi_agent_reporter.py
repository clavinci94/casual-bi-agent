"""Tests for the Reporter-Lead and the LLM ReportSynthesizer sub-worker.

Default tests use a stub Anthropic client (no network). A @pytest.mark.live
test goes against real Claude when ANTHROPIC_API_KEY is set.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from biq.agents.multi.leads.reporter import reporter_node
from biq.agents.multi.state import (
    AnalysisResult,
    CausalEstimate,
    Finding,
    StrategyOption,
    StrategyResult,
)
from biq.agents.multi.sub import report_synthesizer

# --- Helpers -------------------------------------------------------------


def _stub_client(tool_input: dict):
    block = SimpleNamespace(type="tool_use", name="submit_report", input=tool_input)
    usage = SimpleNamespace(
        input_tokens=200,
        output_tokens=120,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    resp = SimpleNamespace(content=[block], stop_reason="tool_use", usage=usage)
    messages = SimpleNamespace(create=lambda **kwargs: resp)
    return SimpleNamespace(messages=messages)


def _stub_client_no_tool_use():
    block = SimpleNamespace(type="text", text="Sorry, no idea.")
    resp = SimpleNamespace(content=[block], stop_reason="end_turn", usage=None)
    messages = SimpleNamespace(create=lambda **kwargs: resp)
    return SimpleNamespace(messages=messages)


VALID_PAYLOAD = {
    "headline_de": "Mobile-Conversion seit 15.04. um 51% eingebrochen",
    "summary_de": (
        "Mobile-Checkout zeigt seit Mitte April einen kausal nachweisbaren "
        "Conversion-Einbruch (-49%, p<0.001). Desktop/Tablet sind nicht "
        "betroffen, was auf eine mobile-spezifische Änderung hindeutet. "
        "Erster Schritt: Mobile-Deployments ab dem 14./15.04. prüfen."
    ),
    "confidence": 0.85,
    "risk_level": "high",
}


def _analysis_with_real_data() -> AnalysisResult:
    return AnalysisResult(
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
                treatment="window 2018-04-15..05-10",
                outcome="conversion (mobile)",
                estimate=-0.49,
                p_value=0.001,
            )
        ],
    )


def _strategy_with_options() -> StrategyResult:
    return StrategyResult(
        options=[
            StrategyOption(
                title="Sofort-Diagnose Mobile-Deployments",
                body_de="Änderungsprotokoll für den 14./15.04. lückenlos aufarbeiten.",
                expected_impact_de="Ursache identifizieren als Grundlage für alle weiteren Schritte.",
                risks_de=["Unvollständiges Protokoll erschwert Zuordnung"],
                effort="low",
            )
        ],
        risk_level="high",
    )


# --- Sub-worker tests ---------------------------------------------------


def test_synthesizer_returns_parsed_report_with_stub_client() -> None:
    result = report_synthesizer.run(
        question="Was tun?",
        analysis=_analysis_with_real_data(),
        strategy=_strategy_with_options(),
        open_questions=[],
        client=_stub_client(VALID_PAYLOAD),
    )
    assert not result.skipped
    assert result.report is not None
    assert "eingebrochen" in result.report.headline_de
    assert result.report.confidence == 0.85
    assert result.report.risk_level == "high"
    # The reporter never invents options — it must reuse the strategist's.
    assert len(result.report.top_options) == 1
    assert result.report.top_options[0].title.startswith("Sofort-Diagnose")


def test_synthesizer_handles_tool_use_missing() -> None:
    result = report_synthesizer.run(
        question="Was tun?",
        analysis=_analysis_with_real_data(),
        strategy=_strategy_with_options(),
        open_questions=[],
        client=_stub_client_no_tool_use(),
    )
    assert result.skipped
    assert "did not call submit_report" in (result.notes or "")


def test_synthesizer_handles_invalid_payload() -> None:
    bad = {"headline_de": "x", "summary_de": "y"}  # missing confidence + risk_level
    result = report_synthesizer.run(
        question=None,
        analysis=_analysis_with_real_data(),
        strategy=_strategy_with_options(),
        open_questions=[],
        client=_stub_client(bad),
    )
    assert result.skipped
    assert (
        "validation" in (result.notes or "").lower() or "keyerror" in (result.notes or "").lower()
    )


# --- Reporter-Lead tests ------------------------------------------------


def test_reporter_falls_back_to_placeholder_when_synthesizer_skips(monkeypatch) -> None:
    """Skipped synthesizer must produce the deterministic placeholder."""
    monkeypatch.setattr(
        report_synthesizer,
        "run",
        lambda **kw: report_synthesizer.ReportSubResult(skipped=True, notes="forced skip"),
    )
    patch = reporter_node(
        {
            "question": "Wieso ist es kaputt?",
            "strategy": _strategy_with_options(),
            "analysis": _analysis_with_real_data(),
        }
    )
    report = patch["report"]
    assert report.headline_de == "Analyse abgeschlossen"
    assert "Wieso ist es kaputt?" in report.summary_de
    # Top-options propagate even on fallback path.
    assert report.top_options[0].title.startswith("Sofort-Diagnose")


def test_reporter_uses_llm_report_when_available(monkeypatch) -> None:
    """Successful synthesis must surface the LLM-produced narrative."""
    from biq.agents.multi.state import ReportResult

    fake = ReportResult(
        headline_de="Echte Headline",
        summary_de="Echter zwei-Satz-Bericht.",
        top_options=_strategy_with_options().options[:3],
        confidence=0.77,
        risk_level="high",
    )
    monkeypatch.setattr(
        report_synthesizer,
        "run",
        lambda **kw: report_synthesizer.ReportSubResult(report=fake, notes="ok"),
    )
    patch = reporter_node(
        {
            "question": "Test",
            "strategy": _strategy_with_options(),
            "analysis": _analysis_with_real_data(),
        }
    )
    assert patch["report"].headline_de == "Echte Headline"
    assert patch["report"].confidence == 0.77


# --- Live (real Claude) — opt-in ----------------------------------------


@pytest.mark.live
def test_synthesizer_against_real_claude() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    result = report_synthesizer.run(
        question="Warum ist conversion auf mobile eingebrochen?",
        analysis=_analysis_with_real_data(),
        strategy=_strategy_with_options(),
        open_questions=[],
    )
    assert not result.skipped, result.notes
    assert result.report is not None
    assert result.report.headline_de
    assert result.report.headline_de != "Analyse abgeschlossen"
    assert 0.0 <= result.report.confidence <= 1.0
    assert result.report.risk_level in ("low", "medium", "high")
