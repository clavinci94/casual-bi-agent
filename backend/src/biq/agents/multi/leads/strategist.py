"""Strategist-Lead: turns the Analyst's findings into actionable options.

Wraps a single OptionGenerator sub-worker. A separate RiskAssessor sub-worker
can be added if blind reviews show the generator under-weights risks — for
now we trust the single LLM call to emit risks inline (cheaper, more
coherent, easier to audit).

The Lead is also responsible for the *escalation* call: if any single
CausalEstimate is large + significant (|rel_effect| > 25% with p < 0.05),
the resulting StrategyResult is at minimum risk_level='high', even if the
LLM softened it.
"""

from __future__ import annotations

from typing import Any

from biq.agents.multi.audit import audit_lead
from biq.agents.multi.state import GlobalState, StrategyResult
from biq.agents.multi.sub import option_generator
from biq.agents.multi.supervisor import mark_completed

SIGNIFICANT_REL_EFFECT = 0.25
SIGNIFICANT_P_VALUE = 0.05


def _has_high_impact_finding(analysis_estimates: list[Any]) -> bool:
    for est in analysis_estimates:
        rel = getattr(est, "estimate", None)
        p = getattr(est, "p_value", None)
        if rel is None:
            continue
        if abs(rel) >= SIGNIFICANT_REL_EFFECT and (p is None or p <= SIGNIFICANT_P_VALUE):
            return True
    return False


def _escalate_if_needed(llm_risk: str, has_high_impact: bool) -> str:
    if has_high_impact and llm_risk != "high":
        return "high"
    return llm_risk


def strategist_node(state: GlobalState) -> dict[str, Any]:
    analysis = state.get("analysis")

    with audit_lead(
        agent_name="strategist",
        action="propose",
        input={
            "has_analysis": analysis is not None,
            "findings_in": len(analysis.findings) if analysis else 0,
            "estimates_in": len(analysis.causal_estimates) if analysis else 0,
        },
    ) as tel:
        if analysis is None:
            tel["output"] = {"skipped": True, "reason": "no_analysis"}
            return {
                "strategy": StrategyResult(
                    notes="strategist skipped: no analysis in state",
                ),
                **mark_completed(state, "strategy"),
            }

        sub = option_generator.run(
            analysis=analysis,
            question=state.get("question"),
        )

        risk_level = _escalate_if_needed(
            sub.risk_level if not sub.skipped else "medium",
            _has_high_impact_finding(analysis.causal_estimates),
        )

        notes_parts: list[str] = []
        if sub.notes:
            notes_parts.append(sub.notes)
        if sub.skipped:
            notes_parts.append("option generator was skipped")
        if risk_level == "high" and (sub.skipped or sub.risk_level != "high"):
            notes_parts.append("risk_level escalated to 'high' by high-impact causal estimate")

        tel["output"] = {
            "options_count": len(sub.options),
            "risk_level": risk_level,
            "option_generator_skipped": sub.skipped,
        }
        return {
            "strategy": StrategyResult(
                options=list(sub.options),
                risk_level=risk_level,
                notes=" | ".join(notes_parts) or None,
            ),
            **mark_completed(state, "strategy"),
        }
