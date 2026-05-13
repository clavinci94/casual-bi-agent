"""Quick visual sanity check on the Tagesbriefing.

Prints the headline + each signal as Worum/Warum/Aktion to stdout.
Costs one Sonnet call (~CHF 0.10) — don't run in a tight loop.

    make briefing-smoke
"""

from __future__ import annotations

import sys
import time

from biq.agents.briefing import generate_briefing, validate_briefing_shape


def main() -> int:
    print("Generating fresh briefing (this takes 15-25 s)…")
    t0 = time.time()
    result = generate_briefing(force_refresh=True)
    dt = time.time() - t0

    run_id = result["run_id"]
    briefing = result["briefing"]

    print(f"\nrun_id     : {run_id}")
    print(f"latency    : {dt:.1f} s")
    print(f"from_cache : {result['from_cache']}")
    print()
    print("Headline   :")
    print(f"  {briefing.get('headline')}")
    print()

    signals = briefing.get("signals", [])
    print(f"Signals    : {len(signals)}")
    for i, s in enumerate(signals, 1):
        print(f"\n  --- Signal {i}  ({s.get('urgency', '?'):6s} · {s.get('source', '?')}) ---")
        print(f"  Was   : {s.get('what')}")
        print(f"  Warum : {s.get('why_for_you')}")
        print(f"  Aktion: {s.get('action')}")

    defects = validate_briefing_shape(briefing)
    print()
    if defects:
        print("STRUCTURAL DEFECTS:")
        for d in defects:
            print(f"  • {d}")
        return 1
    print("structural check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
