"""Run the LangGraph multi-agent investigator.

Default args target the simulated mobile_v2 bug window. End-to-end uses
the same biq.tools.* + R service as the rest of the system.

Usage:
    uv run python scripts/graph_investigate.py
    uv run python scripts/graph_investigate.py --device mobile \\
        --pre 2018-02-15:2018-04-14 --post 2018-04-15:2018-05-10
"""

from __future__ import annotations

import argparse
import json

from biq.agents.graph import run_graph


def _period(s: str) -> tuple[str, str]:
    a, b = s.split(":", 1)
    return (a, b)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="mobile")
    parser.add_argument("--pre", type=_period, default=("2018-02-15", "2018-04-14"))
    parser.add_argument("--post", type=_period, default=("2018-04-15", "2018-05-10"))
    parser.add_argument("--question", default=None)
    args = parser.parse_args()

    result = run_graph(
        target_device=args.device,
        pre_period=args.pre,
        post_period=args.post,
        question=args.question,
    )

    summary = {k: v for k, v in result.items() if k not in ("anomalies", "treatments", "causal_estimate")}
    print(json.dumps(summary, indent=2, default=str))

    n_anom = len(result.get("anomalies", []))
    n_treat = len(result.get("treatments", []))
    causal = result.get("causal_estimate") or {}
    print(f"\nanomalies considered: {n_anom}, treatments considered: {n_treat}")
    if causal.get("rel_effect") is not None:
        print(
            f"causal estimate: rel_effect = {causal['rel_effect']:+.2%}  "
            f"p = {causal.get('p_value'):.4f}  "
            f"significant = {causal.get('is_significant')}"
        )

    if result.get("review_passed"):
        print(f"\nreview PASSED. recommendation: {result.get('rec_id')}")
    else:
        print(
            f"\nreview REJECTED after {result.get('retries')} retries: "
            f"{result.get('review_comments')}"
        )


if __name__ == "__main__":
    main()
