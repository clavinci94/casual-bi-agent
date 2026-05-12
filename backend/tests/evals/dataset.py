"""Eval dataset.

A handful of investigation prompts spanning the failure modes we care
about. Keep this small — each entry is one real Anthropic API call, so
the dataset doubles as a cost knob.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EvalCase:
    name: str
    question: str
    # Soft minimums the judge should beat for this case. Tunable.
    min_factuality: int = 4
    min_causal_rigor: int = 4
    min_actionability: int = 3
    notes: str = ""


CASES: list[EvalCase] = [
    EvalCase(
        name="mobile_v2_regression_with_causal",
        question=(
            "Mobile conversion dropped in early May 2018. Find the cause and recommend an action."
        ),
        notes=(
            "Gold: rel_mobile_v2 release, ~-38 % effect, sensitivity should "
            "land in the robust band."
        ),
    ),
    EvalCase(
        name="no_anomaly_quiet_period",
        question="Anything noteworthy in the conversion data for late February 2018?",
        min_causal_rigor=4,
        notes=(
            "Gold: nothing flagged. Tests whether the agent resists "
            "fabricating causes when none are present."
        ),
    ),
]
