"""End-to-end quality eval for the Tagesbriefing agent.

Costs real money: one Sonnet briefing synthesis + one Haiku judge run
(~CHF 0.10-0.15 total). Marked `eval` so it's opt-in:

    make evals
"""

from __future__ import annotations

import pytest

from biq.agents.briefing import generate_briefing
from biq.config import settings
from tests.evals.briefing_judge import load_briefing_trace, score, structural_check

_HAS_KEY = bool(settings.anthropic_api_key)

# Minimum bar each axis must clear for the suite to stay green. Tunable.
# `factuality` is the strictest — hallucinated numbers are the failure
# mode we care most about; specificity/actionability can be slightly
# softer because they involve more subjective judgment.
MIN_FACTUALITY = 4
MIN_SPECIFICITY = 3
MIN_ACTIONABILITY = 3


@pytest.mark.eval
@pytest.mark.causal  # touches the R service indirectly via signal fetches
def test_briefing_quality(db_ready: bool) -> None:  # type: ignore[no-untyped-def]
    if not _HAS_KEY:
        pytest.skip("ANTHROPIC_API_KEY required for the briefing eval.")

    result = generate_briefing(force_refresh=True)
    run_id = result["run_id"]
    briefing = result["briefing"]

    # 1. Structural gate — cheap, no model call.
    defects = structural_check(briefing)
    assert not defects, f"briefing structural defects: {defects}"

    # 2. LLM judge.
    trace = load_briefing_trace(run_id)
    s = score(trace)

    print(
        f"\n[briefing_quality] factuality={s.factuality} "
        f"specificity={s.specificity} action={s.actionability} "
        f"avg={s.average:.2f}"
    )
    print(f"  factuality:    {s.factuality_reason}")
    print(f"  specificity:   {s.specificity_reason}")
    print(f"  actionability: {s.actionability_reason}")

    assert s.factuality >= MIN_FACTUALITY, (
        f"factuality {s.factuality} < {MIN_FACTUALITY}: {s.factuality_reason}"
    )
    assert s.specificity >= MIN_SPECIFICITY, (
        f"specificity {s.specificity} < {MIN_SPECIFICITY}: {s.specificity_reason}"
    )
    assert s.actionability >= MIN_ACTIONABILITY, (
        f"actionability {s.actionability} < {MIN_ACTIONABILITY}: {s.actionability_reason}"
    )
