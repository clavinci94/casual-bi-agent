"""LLM-as-judge scorer for investigator outputs.

Reads back an investigator run from the audit log (run_id), assembles
the trace (question -> tool calls -> final answer -> recommendation),
and asks Claude Haiku to score it on three rubrics:

  factuality        — do quoted numbers match what the tools returned?
  causal_rigor      — appropriate use of correlation vs causation language,
                      backed by CI / p-value / E-value / power when claimed?
  actionability     — concrete next step + measurable success criterion?

Scores are forced through a `submit_score` tool so the judge cannot
free-form its way around the rubric. Haiku is roughly 5x cheaper than
Sonnet — a judge pass costs ~CHF 0.01.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic
from sqlalchemy import text

from biq.db import engine

JUDGE_MODEL = os.environ.get("BIQ_JUDGE_MODEL", "claude-haiku-4-5-20251001")

JUDGE_SYSTEM = """You are an evaluator for an autonomous Business Intelligence
investigator agent. Your job is to score one investigation on three axes.

Rules:
- Score each axis 1-5 (1 = unacceptable, 3 = adequate, 5 = exemplary).
- You MUST submit your verdict via the `submit_score` tool. Free-form
  answers without the tool call do not count.
- Be strict on factuality: any quoted number that does NOT appear in the
  tool outputs is a 1 or 2, even if the rest of the answer is fine.
- Be strict on causal_rigor: "caused by" without CI + p-value + a
  sensitivity check (E-value) is at most a 3. "Correlated with" is fine
  when no causal tool was called.
- Actionability: a finding without a concrete next step and a measurable
  follow-up KPI is at most a 3.
"""


SCORE_TOOL = {
    "name": "submit_score",
    "description": "Submit your numeric scores and a one-sentence justification per axis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "factuality": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "Do the quoted numbers match the tool outputs?",
            },
            "factuality_reason": {"type": "string"},
            "causal_rigor": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "Correlation vs causation language used appropriately?",
            },
            "causal_rigor_reason": {"type": "string"},
            "actionability": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "Concrete, measurable next step?",
            },
            "actionability_reason": {"type": "string"},
        },
        "required": [
            "factuality",
            "factuality_reason",
            "causal_rigor",
            "causal_rigor_reason",
            "actionability",
            "actionability_reason",
        ],
    },
}


@dataclass
class Trace:
    """The shape we hand to the judge — a single investigation, flattened."""

    question: str
    plan: str | None
    tool_calls: list[dict[str, Any]]
    final_answer: str
    recommendations: list[dict[str, Any]]


@dataclass
class Score:
    factuality: int
    factuality_reason: str
    causal_rigor: int
    causal_rigor_reason: str
    actionability: int
    actionability_reason: str

    @property
    def average(self) -> float:
        return (self.factuality + self.causal_rigor + self.actionability) / 3


def load_trace(run_id: str, final_answer: str) -> Trace:
    """Pull all the audit-side context for one investigation."""
    with engine.connect() as conn:
        run_row = conn.execute(
            text("SELECT prompt FROM audit.agent_runs WHERE run_id = :id"),
            {"id": run_id},
        ).one()
        question = run_row[0] or ""

        plan_row = conn.execute(
            text(
                "SELECT output->>'plan' FROM audit.agent_steps "
                "WHERE run_id = :id AND action = 'plan' LIMIT 1"
            ),
            {"id": run_id},
        ).first()
        plan = plan_row[0] if plan_row else None

        tool_rows = conn.execute(
            text(
                "SELECT s.action, t.tool_name, t.params, t.result_summary, "
                "       t.rows_count, t.error "
                "FROM audit.agent_steps s "
                "JOIN audit.tool_calls t ON t.step_id = s.step_id "
                "WHERE s.run_id = :id "
                "ORDER BY s.started_at"
            ),
            {"id": run_id},
        ).fetchall()

        rec_rows = conn.execute(
            text(
                "SELECT title, body, confidence, risk_level "
                "FROM audit.recommendations WHERE run_id = :id "
                "ORDER BY created_at"
            ),
            {"id": run_id},
        ).fetchall()

    return Trace(
        question=question,
        plan=plan,
        tool_calls=[
            {
                "action": r[0],
                "tool": r[1],
                "params": r[2],
                "result_summary": r[3],
                "rows": r[4],
                "error": r[5],
            }
            for r in tool_rows
        ],
        final_answer=final_answer,
        recommendations=[
            {"title": r[0], "body": r[1], "confidence": r[2], "risk_level": r[3]} for r in rec_rows
        ],
    )


def score(trace: Trace, *, api_key: str | None = None) -> Score:
    """Send a trace to Haiku and parse the structured score."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY required to run the judge.")

    client = Anthropic(api_key=key)

    user_msg = json.dumps(
        {
            "question": trace.question,
            "plan": trace.plan,
            "tool_calls": trace.tool_calls,
            "final_answer": trace.final_answer,
            "recommendations": trace.recommendations,
        },
        default=str,
        indent=2,
    )[:30_000]  # generous cap; Haiku context is plenty

    resp = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=2048,
        system=JUDGE_SYSTEM,
        tools=[SCORE_TOOL],
        tool_choice={"type": "tool", "name": "submit_score"},
        messages=[
            {
                "role": "user",
                "content": (
                    "Score this investigation. The JSON below is the full "
                    "agent trace.\n\n" + user_msg
                ),
            }
        ],
    )

    for block in resp.content:
        if block.type == "tool_use" and block.name == "submit_score":
            d = dict(block.input)
            return Score(
                factuality=int(d["factuality"]),
                factuality_reason=str(d["factuality_reason"]),
                causal_rigor=int(d["causal_rigor"]),
                causal_rigor_reason=str(d["causal_rigor_reason"]),
                actionability=int(d["actionability"]),
                actionability_reason=str(d["actionability_reason"]),
            )

    raise RuntimeError(f"judge did not call submit_score (stop_reason={resp.stop_reason})")
