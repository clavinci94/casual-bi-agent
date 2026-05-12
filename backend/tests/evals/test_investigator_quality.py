"""End-to-end quality eval — runs the real investigator + Claude-as-judge.

Costs real money on every run (Sonnet investigator + Haiku judge).
Marked `eval` so it's opt-in:

    DATABASE_URL=... uv run pytest -m eval        # backend dir
    make evals                                    # if a target is added

CI does NOT run these — the unit-test suite (`pytest -m "not causal and not eval"`)
stays free + deterministic.
"""

from __future__ import annotations

import pytest

from biq.agents.investigator import investigate
from biq.config import settings
from tests.evals.dataset import CASES
from tests.evals.judge import load_trace, score

# Pydantic-settings already loads .env, so this respects backend/.env even
# when pytest is invoked without an explicit ANTHROPIC_API_KEY env var.
_HAS_KEY = bool(settings.anthropic_api_key)


@pytest.mark.eval
@pytest.mark.causal  # the investigator calls the R service
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_investigation_quality(case, db_ready: bool) -> None:  # type: ignore[no-untyped-def]
    if not _HAS_KEY:
        pytest.skip("ANTHROPIC_API_KEY required for eval suite.")

    result = investigate(
        case.question,
        max_iterations=8,
        # Tight budget so an off-the-rails run still costs cents, not francs.
        max_input_tokens=80_000,
        max_output_tokens=8_000,
    )
    assert "error" not in result, result.get("error")
    assert result.get("final_answer"), "investigator returned no final_answer"

    trace = load_trace(result["run_id"], result["final_answer"])
    s = score(trace)

    print(
        f"\n[{case.name}] factuality={s.factuality} causal={s.causal_rigor} "
        f"action={s.actionability} avg={s.average:.2f}"
    )
    print(f"  factuality:    {s.factuality_reason}")
    print(f"  causal_rigor:  {s.causal_rigor_reason}")
    print(f"  actionability: {s.actionability_reason}")

    assert s.factuality >= case.min_factuality, (
        f"factuality {s.factuality} < {case.min_factuality}: {s.factuality_reason}"
    )
    assert s.causal_rigor >= case.min_causal_rigor, (
        f"causal_rigor {s.causal_rigor} < {case.min_causal_rigor}: {s.causal_rigor_reason}"
    )
    assert s.actionability >= case.min_actionability, (
        f"actionability {s.actionability} < {case.min_actionability}: {s.actionability_reason}"
    )
