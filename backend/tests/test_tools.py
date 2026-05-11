"""Tool-layer tests. Same functions called by both heuristic + LLM agents
and exposed via MCP — single source of truth."""

from __future__ import annotations

import pytest

from biq.tools import context as ctx_tools
from biq.tools import kpi as kpi_tools


def test_kpi_query_rejects_unknown_view(db_ready: bool) -> None:
    result = kpi_tools.kpi_query(
        view="not_a_view", start="2018-04-01", end="2018-05-01"
    )
    assert "error" in result
    assert "not allowed" in result["error"]


def test_kpi_query_returns_records(db_ready: bool) -> None:
    result = kpi_tools.kpi_query(
        view="conversion_rate_daily",
        start="2018-04-15",
        end="2018-05-10",
        group_by=["device"],
    )
    assert result["row_count"] > 0
    devices = {r["device"] for r in result["rows"]}
    assert {"mobile", "desktop", "tablet"} <= devices


def test_releases_in_window_finds_mobile_v2(db_ready: bool) -> None:
    result = ctx_tools.releases_in_window(start="2018-04-15", end="2018-05-10")
    ids = [r["release_id"] for r in result["rows"]]
    assert "rel_mobile_v2" in ids, ids


def test_campaigns_in_window_returns_dicts(db_ready: bool) -> None:
    result = ctx_tools.campaigns_in_window(start="2018-03-01", end="2018-06-01")
    assert result["row_count"] >= 0
    for r in result["rows"]:
        assert "campaign_id" in r
        assert "channel" in r


@pytest.mark.causal
def test_causal_impact_matches_ground_truth(db_ready: bool) -> None:
    """End-to-end: Python tool → R service → CausalImpact → expected effect.

    Skipped unless the R service is up (`make r-up`).
    """
    from biq.tools import causal as causal_tools

    h = causal_tools.health()
    if h.get("status") != "ok":
        pytest.skip(f"R service not reachable: {h}")

    result = causal_tools.causal_impact_conversion(
        target_device="mobile",
        pre_start="2018-02-15",
        pre_end="2018-04-14",
        post_start="2018-04-15",
        post_end="2018-05-10",
        controls=["desktop", "tablet"],
    )

    assert "error" not in result, result
    rel = result["rel_effect"]
    assert rel is not None
    # Ground truth: ~-40% from the simulator. Allow generous band.
    assert -0.70 <= rel <= -0.10, f"rel_effect {rel} outside expected band"
    assert result["is_significant"], result
