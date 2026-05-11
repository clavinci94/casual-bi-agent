"""Smoke test the causal layer end-to-end.

Runs CausalImpact on the simulated mobile_checkout_v2 regression window,
using desktop+tablet as synthetic controls. Asserts that:

  - the R service is reachable
  - the estimated relative effect is clearly negative (large drop)
  - the result is statistically significant (p < 0.05)

The ground truth in the simulator is roughly -40% on mobile conversion
during the 25-day bug window. CausalImpact should land in that ballpark.

Usage:
    uv run python scripts/causal_smoke.py
"""

from __future__ import annotations

import json
import sys

from biq.tools import causal as causal_tools


def main() -> int:
    h = causal_tools.health()
    print(f"r-service health: {h}")
    if h.get("status") != "ok":
        print("r-service not reachable. Try: make r-up", file=sys.stderr)
        return 1

    result = causal_tools.causal_impact_conversion(
        target_device="mobile",
        pre_start="2018-02-15",
        pre_end="2018-04-14",
        post_start="2018-04-15",
        post_end="2018-05-10",
        controls=["desktop", "tablet"],
    )

    print(json.dumps(result, indent=2, default=str))

    if "error" in result:
        print(f"\nFAIL: {result['error']}", file=sys.stderr)
        return 1

    rel = result.get("rel_effect")
    p = result.get("p_value")
    sig = result.get("is_significant")

    print(
        f"\nrel_effect = {rel:+.2%}  "
        f"95% CI [{result['rel_effect_lower_95ci']:+.2%}, "
        f"{result['rel_effect_upper_95ci']:+.2%}]  "
        f"p = {p:.4f}  "
        f"significant = {sig}"
    )

    if rel is None:
        print("FAIL: no rel_effect returned", file=sys.stderr)
        return 1

    # Ground truth is -40% ish. Accept anything between -10% and -70% as
    # the synthetic controls + Bayesian smoothing add some variance.
    if not (-0.70 <= rel <= -0.10):
        print(
            f"FAIL: rel_effect {rel:+.2%} not in expected band [-70%, -10%]",
            file=sys.stderr,
        )
        return 1

    if not sig:
        print("FAIL: effect not significant at p<0.05", file=sys.stderr)
        return 1

    print("\nCausal smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
