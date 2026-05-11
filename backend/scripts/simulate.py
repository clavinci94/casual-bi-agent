"""CLI wrapper around biq.seeders.synthetic for generating the full-scale
simulated extensions (releases, campaigns, web_events, support_tickets)
anchored on the real Olist orders.

Usage:
    uv run python scripts/simulate.py --all
    uv run python scripts/simulate.py --all --scale 0.3
    uv run python scripts/simulate.py --all --truncate
    uv run python scripts/simulate.py --web-events --scale 1.0
"""

from __future__ import annotations

import argparse

import numpy as np

from biq.config import settings
from biq.seeders.synthetic import (
    gen_campaigns,
    gen_releases,
    gen_support_tickets,
    gen_web_events,
    truncate_targets,
    write,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic extension data")
    parser.add_argument("--all", action="store_true", help="Generate all four tables")
    parser.add_argument("--releases", action="store_true")
    parser.add_argument("--campaigns", action="store_true")
    parser.add_argument("--web-events", action="store_true", dest="web_events")
    parser.add_argument("--support-tickets", action="store_true", dest="support_tickets")
    parser.add_argument(
        "--scale",
        type=float,
        default=0.3,
        help="Fraction of orders used as web-event anchors (0..1). Default 0.3.",
    )
    parser.add_argument("--n-tickets", type=int, default=5000, dest="n_tickets")
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Truncate target tables before writing",
    )
    args = parser.parse_args()

    do_all = args.all or not (
        args.releases or args.campaigns or args.web_events or args.support_tickets
    )

    rng = np.random.default_rng(settings.simulation_seed)
    print(f"SIMULATION_SEED = {settings.simulation_seed}")

    targets: list[tuple[str, str]] = []
    if do_all or args.releases:
        targets.append(("raw", "releases"))
    if do_all or args.campaigns:
        targets.append(("raw", "campaigns"))
    if do_all or args.web_events:
        targets.append(("raw", "web_events"))
    if do_all or args.support_tickets:
        targets.append(("raw", "support_tickets"))

    if args.truncate and targets:
        truncate_targets(targets)

    if do_all or args.releases:
        print("\nReleases:")
        write(gen_releases(), "raw", "releases")

    if do_all or args.campaigns:
        print("\nCampaigns:")
        write(gen_campaigns(rng), "raw", "campaigns")

    if do_all or args.web_events:
        print("\nWeb events:")
        write(gen_web_events(rng, args.scale), "raw", "web_events")

    if do_all or args.support_tickets:
        print("\nSupport tickets:")
        write(gen_support_tickets(rng, args.n_tickets), "raw", "support_tickets")

    print("\nDone.")


if __name__ == "__main__":
    main()
