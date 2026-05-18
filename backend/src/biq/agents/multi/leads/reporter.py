"""Reporter-Lead: produces the single manager-facing artefact.

Two paths:
1. LLM synthesis via report_synthesizer sub-worker — yields a real DE
   story card (headline + 2-3 sentence summary, confidence, risk_level).
2. Deterministic placeholder fallback — used when no API key, the LLM
   call fails, or the synthesizer otherwise skips. Keeps the multi-agent
   pipeline always producing *something*.

The reporter never invents new strategy options — it picks the top 3 from
strategy.options as-is. This keeps the chain of responsibility clean
(Strategist owns options, Reporter owns narrative).
"""

from __future__ import annotations

from typing import Any

from biq.agents.multi.audit import audit_lead
from biq.agents.multi.state import (
    AnalysisResult,
    GlobalState,
    ReportResult,
    StrategyResult,
)
from biq.agents.multi.sub import report_synthesizer
from biq.agents.multi.supervisor import mark_completed


def _placeholder_report(
    state: GlobalState, strategy: StrategyResult, open_qs: list[str]
) -> ReportResult:
    """Deterministic fallback when no LLM is available."""
    summary = state.get("question") or "Keine Fragestellung angegeben."
    if open_qs:
        summary += " (Hinweis: " + "; ".join(open_qs) + ")"
    return ReportResult(
        headline_de="Analyse abgeschlossen",
        summary_de=summary,
        top_options=list(strategy.options[:3]),
        confidence=0.5,
        risk_level=strategy.risk_level,
    )


def reporter_node(state: GlobalState) -> dict[str, Any]:
    strategy = state.get("strategy") or StrategyResult()
    analysis = state.get("analysis") or AnalysisResult()
    open_qs = state.get("open_questions") or []
    question = state.get("question")

    with audit_lead(
        agent_name="reporter",
        action="synthesize",
        input={
            "options_in": len(strategy.options),
            "findings_in": len(analysis.findings),
            "estimates_in": len(analysis.causal_estimates),
            "open_questions_count": len(open_qs),
        },
    ) as tel:
        sub = report_synthesizer.run(
            question=question,
            analysis=analysis,
            strategy=strategy,
            open_questions=open_qs,
        )
        if sub.skipped or sub.report is None:
            report = _placeholder_report(state, strategy, open_qs)
            origin = "placeholder"
        else:
            report = sub.report
            origin = "llm"

        # Persist the full manager-facing artefact + the options the strategist
        # chose into the reporter's audit row. Downstream API readers fetch
        # everything they need from this single jsonb blob — no need to
        # re-stitch state from earlier rows.
        tel["output"] = {
            "origin": origin,
            "report": report.model_dump(mode="json"),
            "strategy_options": [o.model_dump(mode="json") for o in strategy.options],
            "strategy_risk_level": strategy.risk_level,
            "strategy_notes": strategy.notes,
            "open_questions": open_qs,
            "synth_notes": sub.notes,
        }
        return {
            "report": report,
            **mark_completed(state, "reporter"),
        }
