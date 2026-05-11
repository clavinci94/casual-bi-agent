"""Run the anomaly detector once and print the result.

Usage:
    uv run python scripts/detect_anomalies.py
    uv run python scripts/detect_anomalies.py --date 2018-05-05
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from biq.agents.anomaly import run


def _iso_date(s: str) -> date:
    return date.fromisoformat(s)


def main() -> None:
    parser = argparse.ArgumentParser(description="Heuristic KPI anomaly scan")
    parser.add_argument(
        "--date",
        type=_iso_date,
        default=None,
        help="Reference day (default: latest day in kpi.conversion_rate_daily)",
    )
    args = parser.parse_args()

    result = run(reference_day=args.date)
    print(json.dumps(result, indent=2, default=str))

    n = len(result.get("insights", []))
    if n:
        print(
            f"\n{n} anomaly/anomalies above threshold. "
            f"Logged to audit.recommendations under run_id={result['run_id']}."
        )
    else:
        print("\nNo anomalies above threshold.")


if __name__ == "__main__":
    main()
