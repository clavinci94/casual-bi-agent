"""Run the LLM-driven investigator agent.

Requires ANTHROPIC_API_KEY in .env.

Usage:
    uv run python scripts/investigate.py "What happened to mobile conversion in early May 2018?"
    uv run python scripts/investigate.py --model claude-haiku-4-5-20251001 "Why did margin drop in DACH?"
"""

from __future__ import annotations

import argparse
import json

from biq.agents.investigator import (
    DEFAULT_MAX_INPUT_TOKENS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_THINKING_BUDGET,
    investigate,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-driven BI investigator")
    parser.add_argument("question", help="Business question to investigate")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument(
        "--max-input-tokens",
        type=int,
        default=DEFAULT_MAX_INPUT_TOKENS,
        help="Halt after cumulative input tokens exceed this cap.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=DEFAULT_MAX_OUTPUT_TOKENS,
        help="Halt after cumulative output tokens exceed this cap.",
    )
    parser.add_argument(
        "--thinking-budget",
        type=int,
        default=DEFAULT_THINKING_BUDGET,
        help="Per-turn extended-thinking budget (tokens). Must be >=1024.",
    )
    args = parser.parse_args()

    result = investigate(
        args.question,
        model=args.model,
        max_iterations=args.max_iterations,
        max_input_tokens=args.max_input_tokens,
        max_output_tokens=args.max_output_tokens,
        thinking_budget=args.thinking_budget,
    )

    print(
        json.dumps({k: v for k, v in result.items() if k != "final_answer"}, indent=2, default=str)
    )

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
