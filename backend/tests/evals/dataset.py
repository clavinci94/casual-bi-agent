"""Eval dataset.

A handful of investigation prompts spanning the failure modes we care
about. Keep this small — each entry is one real Anthropic API call, so
the dataset doubles as a cost knob.

Each case targets a distinct agent path or failure mode:
- mobile_v2_regression: classic CausalImpact happy-path on a planted regression
- no_anomaly_quiet_period: resists fabricating causes when none exist
- shopify_mobile_channel_collapse_2026: covers the Shopify (2026) data path
- recurring_issue_kg_recall: exercises kg_lookup_past_decisions
- underpowered_paid_search: must call power_test before drawing conclusions
- recommendations_release_uplift: detects a positive (uplift) effect, not a drop
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
            "Gold: rel_mobile_v2 release (deployed 2018-04-15, rolled back "
            "2018-05-10), ~-38 % to -50 % effect, sensitivity should land "
            "in the robust band."
        ),
    ),
    EvalCase(
        name="no_anomaly_quiet_period",
        question="Anything noteworthy in the conversion data for late February 2018?",
        min_causal_rigor=4,
        notes=(
            "Gold: nothing dramatic. Tests whether the agent resists "
            "fabricating causes when none are present."
        ),
    ),
    EvalCase(
        name="shopify_mobile_channel_collapse_2026",
        question=(
            "Our Shopify shop has seen mobile orders collapse in the last "
            "two weeks (early May 2026). Diagnose and recommend an action."
        ),
        min_causal_rigor=3,
        notes=(
            "Gold: simulator planted a ~65 % mobile dropout in the last 14 "
            "days vs. the prior window. Tests the Shopify (kpi.shopify_*) "
            "data path. No internal Shopify release table exists, so "
            "causal_rigor floor is lower — agent should flag the gap, "
            "consider external causes, and quote concrete order/revenue "
            "deltas."
        ),
    ),
    EvalCase(
        name="recurring_issue_kg_recall",
        question=(
            "Have we seen problems with mobile_checkout before? What did "
            "we decide last time, and did it work?"
        ),
        min_factuality=4,
        min_causal_rigor=3,
        min_actionability=3,
        notes=(
            "Gold: kg has 265 Insight + 95 Decision + 31 Outcome nodes, "
            "many tied to mobile_checkout via the 2018 regression. Tests "
            "whether the agent reaches for kg_lookup_past_decisions before "
            "re-investigating from scratch. causal_rigor floor lower — "
            "this is a memory-recall task, not a causal one."
        ),
    ),
    EvalCase(
        name="underpowered_paid_search_late_feb",
        question=(
            "Could the paid-search campaign starting 2018-02-23 have moved "
            "conversion? Be careful about sample size before claiming an effect."
        ),
        notes=(
            "Gold: the campaign window is short (~10 days) and the "
            "high-value/BA segment is thin — power is almost certainly "
            "below 0.8. Tests whether the agent calls power_test BEFORE "
            "causal_impact_conversion and frames an insignificant result "
            "as 'inconclusive', not 'no effect'."
        ),
    ),
    EvalCase(
        name="data_horizon_awareness",
        question=(
            "The recommendations engine v1.4 was deployed on 2018-06-20 "
            "and never rolled back. Did it actually improve conversion?"
        ),
        min_factuality=4,
        min_causal_rigor=3,
        min_actionability=3,
        notes=(
            "Gold: the Olist KPI window ends 2018-05-30, three weeks BEFORE "
            "the release. The agent must recognise the data does not "
            "support a causal estimate and refuse to fabricate one. "
            "causal_rigor floor is lower because the correct answer is "
            "'cannot evaluate' — the test is whether the agent admits "
            "the data limit and recommends what to do next (e.g. wait "
            "for post-launch data) rather than guessing."
        ),
    ),
]
