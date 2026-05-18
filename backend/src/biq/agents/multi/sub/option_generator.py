"""LLM-driven option generator for the Strategist-Lead.

One Claude call with tool-use forces the model to emit a structured list of
StrategyOption objects (German, manager-facing) plus an overall risk_level.
We don't split option-generation and risk-assessment into two LLM hops:
empirically the model produces more coherent risks when it writes them
alongside each option, and one call is cheap (~CHF 0.02) and ~5s on Sonnet.

Robust: missing ANTHROPIC_API_KEY or any client error returns a skipped
OptionSubResult with notes — the Strategist-Lead still produces a
StrategyResult so the manager-facing report never crashes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from biq.agents.multi.audit import audit_sub, usage_from_anthropic
from biq.agents.multi.state import AnalysisResult, StrategyOption
from biq.config import settings

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 2000

SYSTEM_PROMPT = """Du bist Strategie-Beraterin für einen Schweizer Shopify-Plus-Händler.

Du bekommst die Befunde einer Causal-BI-Analyse (Findings + Causal Estimates)
und schlägst 2 bis 4 konkrete Handlungsoptionen vor, die der Manager
abwägen kann. Wichtig:

- Schreibe für eine Geschäftsführerin, nicht für eine Daten-Person.
  Konkret, nüchtern, auf Deutsch — keine englischen Fachbegriffe wenn vermeidbar.
- Jede Option muss aus den Findings/Estimates ableitbar sein. Wenn die
  Datenlage zu dünn ist, sag das explizit und schlage gezielte
  Folgeanalysen vor — NIEMALS spekulieren.
- Für jede Option: erwartete Wirkung in Worten (nicht in Prozent erfinden),
  realistische Risiken, grobe Aufwandsschätzung (low / medium / high).
- Setze risk_level auf 'high', wenn auch nur eine Option das Geschäft
  signifikant gefährden kann (Pricing, Rollback, Lieferanten-Wechsel etc.).

Gib die Antwort AUSSCHLIESSLICH via `submit_strategy` aus. Kein Fliesstext drumherum.
"""

SUBMIT_TOOL = {
    "name": "submit_strategy",
    "description": "Submit the structured strategy proposal for the manager.",
    "input_schema": {
        "type": "object",
        "properties": {
            "options": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Kurzer DE-Titel der Option, max ~60 Zeichen.",
                        },
                        "body_de": {
                            "type": "string",
                            "description": "2-4 Sätze, was konkret zu tun ist und warum.",
                        },
                        "expected_impact_de": {
                            "type": "string",
                            "description": "Erwartete Wirkung in Worten — keine erfundenen Prozentzahlen.",
                        },
                        "risks_de": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Realistische Risiken, je 1 Satz.",
                        },
                        "effort": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                        },
                    },
                    "required": [
                        "title",
                        "body_de",
                        "expected_impact_de",
                        "risks_de",
                        "effort",
                    ],
                },
            },
            "risk_level": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Gesamt-Risikoeinschätzung des Vorschlagspakets.",
            },
        },
        "required": ["options", "risk_level"],
    },
}


@dataclass
class OptionSubResult:
    options: list[StrategyOption] = field(default_factory=list)
    risk_level: str = "medium"
    notes: str | None = None
    skipped: bool = False


def _analysis_to_prompt_payload(analysis: AnalysisResult, question: str | None) -> str:
    """Compact, JSON-shaped evidence payload — keeps the prompt short and stable."""
    payload = {
        "question": question or "(keine Frage angegeben)",
        "findings": [
            {
                "title": f.title,
                "body_de": f.body_de,
                "severity": f.severity,
                "confidence": round(f.confidence, 2),
                "evidence_refs": [e.ref for e in f.evidence],
            }
            for f in analysis.findings
        ],
        "causal_estimates": [
            {
                "method": e.method,
                "treatment": e.treatment,
                "outcome": e.outcome,
                "estimate": e.estimate,
                "ci_lower": e.ci_lower,
                "ci_upper": e.ci_upper,
                "p_value": e.p_value,
                "notes": e.notes,
            }
            for e in analysis.causal_estimates
        ],
        "method_notes": analysis.method_notes,
    }
    return json.dumps(payload, default=str, ensure_ascii=False, indent=2)


def run(
    analysis: AnalysisResult,
    question: str | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    client: Any | None = None,
) -> OptionSubResult:
    """Generate StrategyOptions for `analysis`. Returns skip when LLM unavailable."""
    with audit_sub(
        agent_name="option_generator",
        action="generate_options",
        input={
            "findings_in": len(analysis.findings),
            "estimates_in": len(analysis.causal_estimates),
            "question": question,
        },
        model=model,
    ) as tel:
        result = _run_inner(analysis, question, model, max_tokens, client, tel)
        tel["output"] = {
            "skipped": result.skipped,
            "options_count": len(result.options),
            "risk_level": result.risk_level,
            "notes": result.notes,
        }
        return result


def _run_inner(
    analysis: AnalysisResult,
    question: str | None,
    model: str,
    max_tokens: int,
    client: Any | None,
    tel: dict[str, Any],
) -> OptionSubResult:
    if not analysis.findings and not analysis.causal_estimates:
        return OptionSubResult(
            skipped=True,
            notes="no findings or causal estimates — nothing to strategise on",
        )

    if client is None:
        if not settings.anthropic_api_key:
            return OptionSubResult(
                skipped=True,
                notes="ANTHROPIC_API_KEY not set — skipping LLM call",
            )
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.anthropic_api_key)

    user_payload = _analysis_to_prompt_payload(analysis, question)

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
            tool_choice={"type": "tool", "name": "submit_strategy"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Hier ist die Analyse. Folge dem System-Prompt strikt "
                        "und gib das Strategie-Paket via `submit_strategy` aus.\n\n" + user_payload
                    ),
                }
            ],
        )
    except Exception as e:
        return OptionSubResult(
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
            and getattr(block, "name", None) == "submit_strategy"
        ):
            payload = dict(block.input)
            break

    if payload is None:
        return OptionSubResult(
            skipped=True,
            notes=f"agent did not call submit_strategy (stop_reason={getattr(resp, 'stop_reason', '?')})",
        )

    try:
        options = [StrategyOption(**opt) for opt in payload.get("options", [])]
    except Exception as e:
        return OptionSubResult(
            skipped=True,
            notes=f"tool_use payload failed Pydantic validation: {e}",
        )

    return OptionSubResult(
        options=options,
        risk_level=payload.get("risk_level", "medium"),
        notes=f"generated {len(options)} option(s) via {model}",
    )
