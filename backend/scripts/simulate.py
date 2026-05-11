"""Generate synthetic raw.releases, raw.campaigns, raw.web_events, raw.support_tickets.

Anchors timing and customer_ids to real raw.orders. Reproducible from
SIMULATION_SEED. Includes a deliberately injected anomaly:
'rel_mobile_v2' (2018-04-15 -> 2018-05-10) causes ~40% drop in mobile
conversion rate. Ground truth for the later CausalImpact demo.

Usage:
    uv run python scripts/simulate.py --all
    uv run python scripts/simulate.py --all --scale 0.3
    uv run python scripts/simulate.py --all --truncate
    uv run python scripts/simulate.py --web-events --scale 1.0
"""

from __future__ import annotations

import argparse
import uuid

import numpy as np
import pandas as pd
from sqlalchemy import text

from biq.config import settings
from biq.db import engine

# ---- Distributions ----

DEVICES = np.array(["mobile", "desktop", "tablet"])
DEVICE_P = np.array([0.55, 0.35, 0.10])

CHANNELS = np.array(["organic", "paid_search", "direct", "email", "social"])
CHANNEL_P = np.array([0.25, 0.30, 0.20, 0.15, 0.10])

# Ground-truth treatment window for the causal demo
MOBILE_BUG_START = pd.Timestamp("2018-04-15", tz="UTC")
MOBILE_BUG_END = pd.Timestamp("2018-05-10", tz="UTC")


# ---- Releases ----

def gen_releases() -> pd.DataFrame:
    rows = [
        ("rel_001", "mobile_checkout", "v1.0", "2017-01-15", None,
         "Initial mobile checkout launch."),
        ("rel_002", "search", "v2.1", "2017-06-01", None,
         "New search ranking algorithm."),
        ("rel_003", "desktop_checkout", "v3.0", "2017-09-12", None,
         "Desktop checkout redesign."),
        # The treatment we will rediscover with CausalImpact
        ("rel_mobile_v2", "mobile_checkout", "v2.0", "2018-04-15", "2018-05-10",
         "Regression: ~40% drop in mobile conversion. Rolled back after 25 days. "
         "Postmortem 2018-05-11."),
        ("rel_005", "recommendations", "v1.4", "2018-06-20", None,
         "ML-based product recommendations."),
        ("rel_006", "search", "v2.2", "2018-07-15", None,
         "Search relevance improvements."),
    ]
    df = pd.DataFrame(
        rows,
        columns=["release_id", "component", "version", "released_ts", "rollback_ts", "notes"],
    )
    df["released_ts"] = pd.to_datetime(df["released_ts"], utc=True)
    df["rollback_ts"] = pd.to_datetime(df["rollback_ts"], utc=True)
    return df


# ---- Campaigns ----

def gen_campaigns(rng: np.random.Generator, n: int = 50) -> pd.DataFrame:
    channels = np.array(["paid_search", "social", "email", "display", "partnership"])
    segments = np.array([None, "high_value", "new", "returning"], dtype=object)
    regions = np.array([None, "SP", "RJ", "MG", "RS", "BA"], dtype=object)

    start_window = pd.Timestamp("2016-10-01", tz="UTC")
    days_window = 670  # ~22 months matching Olist range

    starts = start_window + pd.to_timedelta(rng.integers(0, days_window, n), unit="D")
    durations = rng.integers(7, 30, n)
    ends = starts + pd.to_timedelta(durations, unit="D")

    df = pd.DataFrame({
        "campaign_id": [f"cmp_{i:03d}" for i in range(n)],
        "channel": rng.choice(channels, n),
        "target_segment": rng.choice(segments, n),
        "target_region": rng.choice(regions, n),
        "start_ts": starts,
        "end_ts": ends,
        "budget_brl": rng.integers(1000, 50000, n).astype(float),
        "owner": ["marketing"] * n,
    })
    df["name"] = (
        df["channel"].str.replace("_", " ").str.title()
        + " " + df["start_ts"].dt.strftime("%Y-%m")
    )
    df["hypothesis"] = df.apply(
        lambda r: (
            f"Increase {r['channel']} traffic"
            + (f" for {r['target_segment']} segment" if r["target_segment"] else "")
            + (f" in {r['target_region']}" if r["target_region"] else "")
        ),
        axis=1,
    )
    return df[[
        "campaign_id", "name", "channel", "target_segment", "target_region",
        "start_ts", "end_ts", "budget_brl", "hypothesis", "owner",
    ]]


# ---- Web events ----

def _new_uuids(n: int) -> np.ndarray:
    return np.array([str(uuid.uuid4()) for _ in range(n)], dtype=object)


def _position_in_session(counts: np.ndarray) -> np.ndarray:
    """Given session event counts [2,3,1], return positions [0,1,0,1,2,0]."""
    total = int(counts.sum())
    cum = np.cumsum(counts)
    starts = np.repeat(cum - counts, counts)
    return np.arange(total) - starts


def gen_web_events(rng: np.random.Generator, scale: float) -> pd.DataFrame:
    print("  loading raw.orders ...")
    orders = pd.read_sql(
        "select order_id, customer_id, purchase_ts from raw.orders order by purchase_ts",
        engine,
    )
    if len(orders) == 0:
        raise SystemExit("No orders in raw.orders. Run scripts/load_olist.py first.")
    orders["purchase_ts"] = pd.to_datetime(orders["purchase_ts"], utc=True)

    if scale < 1.0:
        orders = orders.sample(
            frac=scale, random_state=int(rng.integers(2**31))
        ).reset_index(drop=True)

    # === Converting sessions: 1 per order, 5 events each ===
    n_conv = len(orders)
    print(f"  converting sessions: {n_conv:,}")

    conv_sids = _new_uuids(n_conv)
    conv_devs = rng.choice(DEVICES, n_conv, p=DEVICE_P)
    conv_chs = rng.choice(CHANNELS, n_conv, p=CHANNEL_P)

    event_types_c = np.array(["page_view", "page_view", "add_to_cart", "begin_checkout", "purchase"])
    pages_c = np.array(["/", "/product", "/product", "/checkout", "/checkout"])
    offsets_c = np.array([-300, -180, -120, -60, 0])

    idx_c = np.repeat(np.arange(n_conv), 5)
    pos_c = np.tile(np.arange(5), n_conv)
    purchase_ts_arr = pd.DatetimeIndex(orders["purchase_ts"]).to_numpy()

    conv_events = pd.DataFrame({
        "session_id": conv_sids[idx_c],
        "customer_id": orders["customer_id"].to_numpy()[idx_c],
        "ts": purchase_ts_arr[idx_c] + pd.to_timedelta(offsets_c[pos_c], unit="s").to_numpy(),
        "event_type": event_types_c[pos_c],
        "page": pages_c[pos_c],
        "product_id": pd.Series([None] * len(idx_c), dtype=object),
        "device": conv_devs[idx_c],
        "channel": conv_chs[idx_c],
        "campaign_id": pd.Series([None] * len(idx_c), dtype=object),
        "country": "BR",
        "is_bot": False,
    })

    # === Non-converting sessions: ~3x converting volume ===
    start_ts = orders["purchase_ts"].min().floor("D")
    end_ts = orders["purchase_ts"].max().ceil("D")
    total_seconds = int((end_ts - start_ts).total_seconds())

    n_nc = n_conv * 3
    print(f"  non-converting sessions: {n_nc:,}")

    nc_offsets = rng.integers(0, total_seconds, n_nc)
    nc_ts_start = start_ts + pd.to_timedelta(nc_offsets, unit="s")
    nc_sids = _new_uuids(n_nc)
    nc_devs = rng.choice(DEVICES, n_nc, p=DEVICE_P)
    nc_chs = rng.choice(CHANNELS, n_nc, p=CHANNEL_P)
    nc_is_bot = rng.random(n_nc) < 0.05
    nc_evcount = rng.integers(1, 6, n_nc)  # 1..5 events per session

    idx_nc = np.repeat(np.arange(n_nc), nc_evcount)
    pos_nc = _position_in_session(nc_evcount)

    # 25% of sessions: last event is add_to_cart (rest stay as page_view)
    last_event_abs_idx = np.cumsum(nc_evcount) - 1
    addcart_mask = rng.random(n_nc) < 0.25
    event_type_nc = np.full(pos_nc.shape[0], "page_view", dtype=object)
    event_type_nc[last_event_abs_idx[addcart_mask]] = "add_to_cart"

    nc_ts_start_arr = pd.DatetimeIndex(nc_ts_start).to_numpy()
    nc_events = pd.DataFrame({
        "session_id": nc_sids[idx_nc],
        "customer_id": pd.Series([None] * len(idx_nc), dtype=object),
        "ts": nc_ts_start_arr[idx_nc] + pd.to_timedelta(pos_nc * 30, unit="s").to_numpy(),
        "event_type": event_type_nc,
        "page": "/",
        "product_id": pd.Series([None] * len(idx_nc), dtype=object),
        "device": nc_devs[idx_nc],
        "channel": nc_chs[idx_nc],
        "campaign_id": pd.Series([None] * len(idx_nc), dtype=object),
        "country": "BR",
        "is_bot": nc_is_bot[idx_nc],
    })

    # === Mobile bug: extra failing mobile sessions during the window ===
    print(f"  mobile_checkout_v2 regression: {MOBILE_BUG_START.date()} -> {MOBILE_BUG_END.date()}")
    days_total = max(1, (end_ts - start_ts).days)
    sessions_per_day = max(1, n_conv // days_total)
    bug_days = (MOBILE_BUG_END - MOBILE_BUG_START).days
    n_bug = int(sessions_per_day * bug_days * 0.5)  # +50% mobile sessions = ~40% conv drop

    bug_offsets = rng.integers(
        0, int((MOBILE_BUG_END - MOBILE_BUG_START).total_seconds()), n_bug
    )
    bug_ts_start = MOBILE_BUG_START + pd.to_timedelta(bug_offsets, unit="s")
    bug_sids = _new_uuids(n_bug)
    bug_chs = rng.choice(CHANNELS, n_bug, p=CHANNEL_P)

    bug_types = np.array(["page_view", "add_to_cart", "begin_checkout", "error"])
    bug_pages = np.array(["/", "/product", "/checkout", "/checkout"])

    idx_b = np.repeat(np.arange(n_bug), 4)
    pos_b = np.tile(np.arange(4), n_bug)

    bug_ts_start_arr = pd.DatetimeIndex(bug_ts_start).to_numpy()
    bug_events = pd.DataFrame({
        "session_id": bug_sids[idx_b],
        "customer_id": pd.Series([None] * len(idx_b), dtype=object),
        "ts": bug_ts_start_arr[idx_b] + pd.to_timedelta(pos_b * 30, unit="s").to_numpy(),
        "event_type": bug_types[pos_b],
        "page": bug_pages[pos_b],
        "product_id": pd.Series([None] * len(idx_b), dtype=object),
        "device": "mobile",
        "channel": bug_chs[idx_b],
        "campaign_id": pd.Series([None] * len(idx_b), dtype=object),
        "country": "BR",
        "is_bot": False,
    })
    print(f"    {n_bug:,} failing mobile sessions added")

    all_events = pd.concat([conv_events, nc_events, bug_events], ignore_index=True)
    all_events = all_events.sort_values("ts").reset_index(drop=True)

    n_sessions = all_events["session_id"].nunique()
    print(f"  total: {len(all_events):,} events across {n_sessions:,} sessions")
    return all_events


# ---- Support tickets ----

TICKET_TEMPLATES: dict[str, list[str]] = {
    "delivery": [
        "Order has not arrived after {} days, status still in transit.",
        "Package delivered to wrong address.",
        "Tracking number does not update for over a week.",
    ],
    "payment": [
        "Card was charged twice for the same order.",
        "Payment failed but order shows as confirmed.",
        "Need invoice for the order, cannot find it in my account.",
    ],
    "product": [
        "Item arrived damaged in the original packaging.",
        "Wrong size received, expected M got XL.",
        "Product does not match the description on the site.",
    ],
    "refund": [
        "Returned item over two weeks ago, still no refund.",
        "Partial refund requested for delayed delivery.",
        "Cancellation request was not processed.",
    ],
    "other": [
        "How do I change my shipping address?",
        "Question about loyalty points expiration.",
        "Cannot log in to my account, password reset email never arrives.",
    ],
}


def gen_support_tickets(rng: np.random.Generator, n: int = 5000) -> pd.DataFrame:
    sample = pd.read_sql(
        text(
            "select order_id, customer_id, purchase_ts from raw.orders "
            "where order_status = 'delivered' "
            f"order by random() limit {n}"
        ),
        engine,
    )
    if len(sample) == 0:
        print("  (no delivered orders; skipping tickets)")
        return pd.DataFrame()

    sample["purchase_ts"] = pd.to_datetime(sample["purchase_ts"], utc=True)
    n = len(sample)
    print(f"  generating {n:,} tickets")

    categories = np.array(["delivery", "payment", "product", "refund", "other"])
    cat_p = np.array([0.40, 0.20, 0.20, 0.12, 0.08])
    priorities = np.array(["low", "medium", "high"])
    prio_p = np.array([0.55, 0.35, 0.10])

    cats = rng.choice(categories, n, p=cat_p)
    texts = [
        rng.choice(TICKET_TEMPLATES[c]).format(int(rng.integers(3, 21)))
        for c in cats
    ]

    open_offsets = rng.integers(1, 30 * 86400, n)
    opened = pd.DatetimeIndex(sample["purchase_ts"]).to_numpy() + pd.to_timedelta(
        open_offsets, unit="s"
    ).to_numpy()

    is_resolved = rng.random(n) < 0.85
    resolve_delta_s = rng.integers(0, 14 * 86400, n).astype(float)
    resolve_delta_s[~is_resolved] = np.nan
    resolved = opened + pd.to_timedelta(resolve_delta_s, unit="s").to_numpy()

    return pd.DataFrame({
        "ticket_id": [f"tkt_{i:06d}" for i in range(n)],
        "customer_id": sample["customer_id"].to_numpy(),
        "order_id": sample["order_id"].to_numpy(),
        "category": cats,
        "priority": rng.choice(priorities, n, p=prio_p),
        "opened_ts": opened,
        "resolved_ts": resolved,
        "text": texts,
    })


# ---- IO ----

def write(df: pd.DataFrame, schema: str, table: str) -> None:
    if df is None or len(df) == 0:
        print(f"  (nothing to write to {schema}.{table})")
        return
    print(f"  writing {len(df):,} rows -> {schema}.{table}")
    df.to_sql(
        table, engine, schema=schema, if_exists="append",
        index=False, method="multi", chunksize=1000,
    )


def truncate_targets(targets: list[tuple[str, str]]) -> None:
    target_str = ", ".join(f"{s}.{t}" for s, t in targets)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {target_str} CASCADE"))
    print(f"Truncated: {target_str}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic extension data")
    parser.add_argument("--all", action="store_true", help="Generate all four tables")
    parser.add_argument("--releases", action="store_true")
    parser.add_argument("--campaigns", action="store_true")
    parser.add_argument("--web-events", action="store_true", dest="web_events")
    parser.add_argument("--support-tickets", action="store_true", dest="support_tickets")
    parser.add_argument(
        "--scale", type=float, default=0.3,
        help="Fraction of orders used as web-event anchors (0..1). Default 0.3.",
    )
    parser.add_argument("--n-tickets", type=int, default=5000, dest="n_tickets")
    parser.add_argument(
        "--truncate", action="store_true",
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
