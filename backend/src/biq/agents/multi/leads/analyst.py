"""Analyst-Lead: orchestrates the descriptive + causal sub-workers.

Consolidates their dataclass outputs into a single AnalysisResult that the
Strategist and Reporter can read. Robust by design: each sub-worker can be
skipped (DB or R service unreachable, empty window) without crashing the
multi-agent run.
"""

from __future__ import annotations

from typing import Any

from biq.agents.multi.audit import audit_lead
from biq.agents.multi.state import AnalysisResult, GlobalState
from biq.agents.multi.sub import causal as causal_sub
from biq.agents.multi.sub import descriptive as descriptive_sub
from biq.agents.multi.supervisor import mark_completed

DEFAULT_TARGET_DEVICE = "mobile"


def _resolve_horizon(state: GlobalState) -> tuple[str, str] | None:
    h = state.get("horizon")
    if h and len(h) == 2:
        return (str(h[0]), str(h[1]))
    return None


def analyst_node(state: GlobalState) -> dict[str, Any]:
    horizon = _resolve_horizon(state)
    target_device = state.get("target_device") or DEFAULT_TARGET_DEVICE
    baseline = state.get("baseline")

    with audit_lead(
        agent_name="analyst",
        action="investigate",
        input={
            "horizon": list(horizon) if horizon else None,
            "baseline": list(baseline) if baseline else None,
            "target_device": target_device,
        },
    ) as tel:
        if horizon is None:
            result = AnalysisResult(
                method_notes=(
                    "analyst skipped: no `horizon` (post-period) provided in state. "
                    "Supervisor should extract the investigation window from the question "
                    "before invoking the analyst lead."
                )
            )
            tel["output"] = {"skipped": True, "reason": "no_horizon"}
            return {"analysis": result, **mark_completed(state, "analyst")}

        desc = descriptive_sub.run(
            horizon=horizon,
            baseline=baseline,
            target_device=target_device,
        )
        causal = causal_sub.run(
            horizon=horizon,
            target_device=target_device,
            baseline=baseline,
        )

        method_notes_parts: list[str] = []
        if desc.notes:
            method_notes_parts.append(f"descriptive: {desc.notes}")
        if causal.notes:
            method_notes_parts.append(f"causal: {causal.notes}")
        if desc.skipped and causal.skipped:
            method_notes_parts.append("both sub-workers skipped — analysis is empty")

        result = AnalysisResult(
            findings=list(desc.findings),
            causal_estimates=list(causal.estimates),
            method_notes=" | ".join(method_notes_parts) or None,
        )
        tel["output"] = {
            "findings_count": len(result.findings),
            "causal_estimates_count": len(result.causal_estimates),
            "descriptive_skipped": desc.skipped,
            "causal_skipped": causal.skipped,
        }
        return {"analysis": result, **mark_completed(state, "analyst")}
