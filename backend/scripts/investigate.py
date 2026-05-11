"""Run the LLM-driven investigator agent.

Requires ANTHROPIC_API_KEY in .env.

Usage:
    uv run python scripts/investigate.py "What happened to mobile conversion in early May 2018?"
    uv run python scripts/investigate.py --model claude-haiku-4-5-20251001 "Why did margin drop in DACH?"
"""

from __future__ import annotations

import argparse
import json

from biq.agents.investigator import DEFAULT_MODEL, investigate


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-driven BI investigator")
    parser.add_argument("question", help="Business question to investigate")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-iterations", type=int, default=10)
    args = parser.parse_args()

    result = investigate(
        args.question,
        model=args.model,
        max_iterations=args.max_iterations,
    )

    print(json.dumps({k: v for k, v in result.items() if k != "final_answer"}, indent=2, default=str))

    if result.get("final_answer"):
        print("\n" + "=" * 70)
        print("FINAL ANSWER")
        print("=" * 70)
        print(result["final_answer"])

    n_rec = len(result.get("recommendation_ids", []))
    if n_rec:
        print(f"\n{n_rec} finding(s) logged to audit.recommendations.")


if __name__ == "__main__":
    main()
