"""LLM-as-judge scorer for Tagesbriefing outputs.

Briefing is structurally different from an investigator run: it is a
single-shot synthesis over six signal blocks, with a strict structured
output (3-5 signals * {what, why_for_you, action, urgency, source}).
The axes that matter are also different — there is no causal claim to
defend, so we drop `causal_rigor`. Instead:

  factuality   — every number / fact in each signal's "what" must
                 appear verbatim in the signal-block data the agent
                 received.
  specificity  — each "why_for_you" must reference shop-specific
                 context (a real channel, KPI value, category, …),
                 not boilerplate that could apply to any shop.
  actionability — each "action" must contain a concrete next step
                  with a measurable criterion or deadline.

Scores forced through `submit_score` tool. Haiku-cheap (~CHF 0.01/run).
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


JUDGE_SYSTEM = """You are evaluating one Tagesbriefing produced by an
autonomous BI agent for a Swiss Shopify-Plus merchant.

Score on three axes 1-5 (1 = unacceptable, 3 = adequate, 5 = exemplary):

1. factuality — every number, percentage, currency amount, date or
   named entity that appears in any signal's `what` or `why_for_you`
   MUST appear verbatim in the input signal blocks under the same source.
   Hallucinated specifics (e.g. citing a market move that isn't in the
   markets block) drop this to 1 or 2.

2. specificity — does each signal's `why_for_you` reference shop-
   specific context? Mentioning real channel names (mobile/desktop/pos),
   real revenue figures from the kpis block, real top-category names,
   real Shopify incidents — that's specific. Generic statements like
   "stable currency helps margin" without naming the shop's actual
   exposure score 3 or below.

3. actionability — does each `action` contain a concrete, measurable
   next step? A clear deadline ("by 14:00 today"), a target metric
   ("≥ 50 mobile orders/week"), or a specific operational verb
   ("test the mobile checkout on iOS 26 device") all count. Vague
   advice like "monitor the situation" without thresholds is at most 3.

Submit via `submit_score`. Free-form answers without the tool call do
not count.
"""


SCORE_TOOL = {
    "name": "submit_score",
    "description": "Submit numeric scores + one-sentence justification per axis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "factuality": {"type": "integer", "minimum": 1, "maximum": 5},
            "factuality_reason": {"type": "string"},
            "specificity": {"type": "integer", "minimum": 1, "maximum": 5},
            "specificity_reason": {"type": "string"},
            "actionability": {"type": "integer", "minimum": 1, "maximum": 5},
            "actionability_reason": {"type": "string"},
        },
        "required": [
            "factuality",
            "factuality_reason",
            "specificity",
            "specificity_reason",
            "actionability",
            "actionability_reason",
        ],
    },
}


@dataclass
class BriefingTrace:
    """All inputs the agent saw + its structured output, flattened."""

    signal_blocks: dict[str, Any]
    briefing: dict[str, Any]


@dataclass
class BriefingScore:
    factuality: int
    factuality_reason: str
    specificity: int
    specificity_reason: str
    actionability: int
    actionability_reason: str

    @property
    def average(self) -> float:
        return (self.factuality + self.specificity + self.actionability) / 3


def load_briefing_trace(run_id: str) -> BriefingTrace:
    """Reconstruct what the agent saw + what it produced.

    The agent's synthesize step persists `compact_signals` on its input
    column — that's the exact bundle Claude saw when writing the
    briefing, so it's the right source-of-truth to verify factuality
    against.  `briefing` itself lives on the same step's output.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT input, output FROM audit.agent_steps "
                "WHERE run_id = :id AND action = 'synthesize' "
                "ORDER BY started_at DESC LIMIT 1"
            ),
            {"id": run_id},
        ).fetchall()

    signal_blocks: dict[str, Any] = {}
    briefing: dict[str, Any] = {}
    if rows:
        input_blob, output_blob = rows[0]
        if isinstance(input_blob, dict):
            cs = input_blob.get("compact_signals")
            if isinstance(cs, dict):
                signal_blocks = cs
        if isinstance(output_blob, dict):
            b = output_blob.get("briefing")
            if isinstance(b, dict):
                briefing = b

    return BriefingTrace(signal_blocks=signal_blocks, briefing=briefing)


# `structural_check` lives in biq.agents.briefing now; re-export for
# back-compat with any local script that imported it from here.
from biq.agents.briefing import validate_briefing_shape as structural_check  # noqa: E402, F401


def score(trace: BriefingTrace, *, api_key: str | None = None) -> BriefingScore:
    """Send a trace to Haiku and parse the structured score."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        try:
            from biq.config import settings

            key = settings.anthropic_api_key
        except Exception:
            key = None
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY required to run the briefing judge.")

    client = Anthropic(api_key=key)

    user_msg = json.dumps(
        {"signal_blocks": trace.signal_blocks, "briefing": trace.briefing},
        default=str,
        indent=2,
        ensure_ascii=False,
    )[:60_000]  # Haiku has room; truncate only on absurdly large payloads.

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
                    "Score this briefing. The JSON below is everything the "
                    "agent saw (signal_blocks) and produced (briefing).\n\n" + user_msg
                ),
            }
        ],
    )

    for block in resp.content:
        if block.type == "tool_use" and block.name == "submit_score":
            d = dict(block.input)
            return BriefingScore(
                factuality=int(d["factuality"]),
                factuality_reason=str(d["factuality_reason"]),
                specificity=int(d["specificity"]),
                specificity_reason=str(d["specificity_reason"]),
                actionability=int(d["actionability"]),
                actionability_reason=str(d["actionability_reason"]),
            )

    raise RuntimeError(f"judge did not call submit_score (stop_reason={resp.stop_reason})")
