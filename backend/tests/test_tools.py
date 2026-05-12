"""Tool-layer tests. Same functions called by both heuristic + LLM agents
and exposed via MCP — single source of truth."""

from __future__ import annotations

import pytest

from biq.tools import context as ctx_tools
from biq.tools import kpi as kpi_tools


def test_kpi_query_rejects_unknown_view(db_ready: bool) -> None:
    result = kpi_tools.kpi_query(view="not_a_view", start="2018-04-01", end="2018-05-01")
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


@pytest.mark.causal
def test_evalue_for_known_effect() -> None:
    """E-value for a -38% effect should land in the 'robust' band (~2-3)."""
    from biq.tools import causal as causal_tools

    h = causal_tools.health()
    if h.get("status") != "ok":
        pytest.skip(f"R service not reachable: {h}")

    out = causal_tools.evalue(rel_effect=-0.384, rel_effect_lower=-0.418)
    assert "error" not in out, out
    assert 2.0 <= out["e_value"] <= 3.5, out
    # CI-bound E-value should be at least as conservative as the point estimate
    # when the CI doesn't cross the null.
    assert out["e_value_ci_bound"] >= out["e_value"], out
    assert "robust" in out["interpretation"]


@pytest.mark.causal
def test_evalue_handles_ci_crossing_null() -> None:
    from biq.tools import causal as causal_tools

    h = causal_tools.health()
    if h.get("status") != "ok":
        pytest.skip(f"R service not reachable: {h}")

    out = causal_tools.evalue(rel_effect=-0.10, rel_effect_lower=0.05)
    assert out["e_value_ci_bound"] == 1.0, out


@pytest.mark.causal
def test_power_solves_for_sample_size() -> None:
    """Detect a 4% → 2.5% drop at 80% power → needs roughly 2k per group."""
    from biq.tools import causal as causal_tools

    h = causal_tools.health()
    if h.get("status") != "ok":
        pytest.skip(f"R service not reachable: {h}")

    out = causal_tools.power_test(p1=0.04, p2=0.025, power=0.80)
    assert "error" not in out, out
    # power.prop.test returns ~2192 here; allow band for numerical wobble.
    assert 1800 <= out["n"] <= 2600, out
    assert abs(out["power"] - 0.80) < 1e-3


@pytest.mark.causal
def test_power_solves_for_power() -> None:
    from biq.tools import causal as causal_tools

    h = causal_tools.health()
    if h.get("status") != "ok":
        pytest.skip(f"R service not reachable: {h}")

    # Tiny sample → power should be far below 0.8.
    out = causal_tools.power_test(p1=0.04, p2=0.025, n=100)
    assert "error" not in out, out
    assert out["power"] < 0.5, out


def test_power_validates_three_required() -> None:
    """Passing fewer than 3 of {n,p1,p2,power} should error before hitting R."""
    from biq.tools import causal as causal_tools

    out = causal_tools.power_test(p1=0.04, p2=0.025)  # only 2 args
    assert "error" in out
    assert "exactly three" in out["error"]
