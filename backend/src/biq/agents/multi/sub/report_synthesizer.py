"""LLM-driven manager-facing report synthesizer.

One Claude tool-use call condenses the analyst findings, causal estimates,
strategist options and any open_questions into a tight German "story card"
the manager can act on in under a minute. Follows the project's UI memo:
icons + story-card + plain German, no engineering jargon.

Robust: skipped (with notes) when ANTHROPIC_API_KEY is missing or the
call fails — the Reporter-Lead then falls back to a deterministic
placeholder so the run still completes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from biq.agents.multi.audit import audit_sub, usage_from_anthropic
from biq.agents.multi.state import (
    AnalysisResult,
    ReportResult,
    StrategyOption,
    StrategyResult,
)
from biq.config import settings

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 1500

SYSTEM_PROMPT = """Du fasst die Befunde einer Causal-BI-Analyse für die Geschäftsführerin
eines Schweizer Shopify-Plus-Händlers in einer kurzen Story-Card zusammen.

Anforderungen:
- Sprache: Deutsch. Keine englischen Fachbegriffe, ausser sie sind im
  Schweizer Business-Alltag etabliert (z. B. "Conversion", "Rollback").
- `headline_de`: EIN informativer Satz, max ~80 Zeichen — was ist passiert
  und wo. NIE "Analyse abgeschlossen" oder Ähnliches.
- `summary_de`: 2 bis 3 Sätze. Beantworte (1) was ist passiert,
  (2) wie sicher sind wir, (3) was empfehlen die Strategie-Optionen
  im Kern. Quantifiziere, wenn die Daten es hergeben.
- `confidence`: 0..1, gewichtet aus den Findings + Causal Estimates.
- `risk_level`: vom Strategist übernehmen, nur abändern wenn die Datenlage
  ein viel zuverlässigeres Bild rechtfertigt.
- `top_options`: Übernehme die ersten 3 Strategie-Optionen unverändert
  (Reporter erfindet keine neuen Optionen).

WICHTIG: Wenn die Datenlage dünn ist oder offene Fragen unbeantwortet
bleiben, sag das in der summary_de explizit — niemals Sicherheit vortäuschen.

Gib die Antwort AUSSCHLIESSLICH via `submit_report` aus.
"""

SUBMIT_TOOL = {
    "name": "submit_report",
    "description": "Submit the final manager-facing story card.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline_de": {
                "type": "string",
                "description": "Ein informativer DE-Satz, was passiert ist (max ~80 Zeichen).",
            },
            "summary_de": {
                "type": "string",
                "description": "2-3 Sätze: was, wie sicher, empfohlene Richtung.",
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "risk_level": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
        },
        "required": ["headline_de", "summary_de", "confidence", "risk_level"],
    },
}


@dataclass
class ReportSubResult:
    report: ReportResult | None = None
    notes: str | None = None
    skipped: bool = False


def _state_to_prompt(
    question: str | None,
    analysis: AnalysisResult,
    strategy: StrategyResult,
    open_questions: list[str],
) -> str:
    """Compact, JSON-shaped briefing for Claude — keeps the prompt stable."""
    return json.dumps(
        {
            "question": question or "(keine Frage angegeben)",
            "findings": [
                {
                    "title": f.title,
                    "body_de": f.body_de,
                    "severity": f.severity,
                    "confidence": round(f.confidence, 2),
                }
                for f in analysis.findings
            ],
            "causal_estimates": [
                {
                    "method": e.method,
                    "treatment": e.treatment,
                    "outcome": e.outcome,
                    "estimate": e.estimate,
                    "p_value": e.p_value,
                    "ci_lower": e.ci_lower,
                    "ci_upper": e.ci_upper,
                }
                for e in analysis.causal_estimates
            ],
            "strategy": {
                "risk_level": strategy.risk_level,
                "options": [
                    {
                        "title": o.title,
                        "body_de": o.body_de,
                        "expected_impact_de": o.expected_impact_de,
                        "risks_de": o.risks_de,
                        "effort": o.effort,
                    }
                    for o in strategy.options
                ],
            },
            "open_questions": open_questions,
        },
        default=str,
        ensure_ascii=False,
        indent=2,
    )


def run(
    question: str | None,
    analysis: AnalysisResult,
    strategy: StrategyResult,
    open_questions: list[str],
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    client: Any | None = None,
) -> ReportSubResult:
    """Synthesize the manager-facing story card. Skip when LLM unavailable."""
    with audit_sub(
        agent_name="report_synthesizer",
        action="synthesize",
        input={
            "findings_in": len(analysis.findings),
            "estimates_in": len(analysis.causal_estimates),
            "options_in": len(strategy.options),
            "open_questions_count": len(open_questions),
            "has_question": question is not None,
        },
        model=model,
    ) as tel:
        result = _run_inner(
            question, analysis, strategy, open_questions, model, max_tokens, client, tel
        )
        tel["output"] = {
            "skipped": result.skipped,
            "notes": result.notes,
            "headline_de": result.report.headline_de if result.report else None,
        }
        return result


def _top_options(strategy: StrategyResult) -> list[StrategyOption]:
    return list(strategy.options[:3])


def _run_inner(
    question: str | None,
    analysis: AnalysisResult,
    strategy: StrategyResult,
    open_questions: list[str],
    model: str,
    max_tokens: int,
    client: Any | None,
    tel: dict[str, Any],
) -> ReportSubResult:
    if client is None:
        if not settings.anthropic_api_key:
            return ReportSubResult(
                skipped=True,
                notes="ANTHROPIC_API_KEY not set — falling back to placeholder",
            )
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.anthropic_api_key)

    user_payload = _state_to_prompt(question, analysis, strategy, open_questions)

    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[SUBMIT_TOOL],
            tool_choice={"type": "tool", "name": "submit_report"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Hier ist die vollständige Analyse + Strategie. "
                        "Folge dem System-Prompt strikt und gib die Story-Card "
                        "via `submit_report` aus.\n\n" + user_payload
                    ),
                }
            ],
        )
    except Exception as e:
        return ReportSubResult(
            skipped=True,
            notes=f"Claude call failed: {type(e).__name__}: {e}",
        )

    tin, tout = usage_from_anthropic(resp)
    tel["tokens_in"] = tin
    tel["tokens_out"] = tout

    payload: dict[str, Any] | None = None
    for block in resp.content:
        if (
            getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == "submit_report"
        ):
            payload = dict(block.input)
            break

    if payload is None:
        return ReportSubResult(
            skipped=True,
            notes=f"agent did not call submit_report (stop_reason={getattr(resp, 'stop_reason', '?')})",
        )

    try:
        report = ReportResult(
            headline_de=payload["headline_de"],
            summary_de=payload["summary_de"],
            top_options=_top_options(strategy),
            confidence=float(payload["confidence"]),
            risk_level=payload["risk_level"],
        )
    except Exception as e:
        return ReportSubResult(
            skipped=True,
            notes=f"tool_use payload failed Pydantic validation: {e}",
        )

    return ReportSubResult(report=report, notes=f"generated via {model}")
