"""Causal BI MCP server.

Exposes the same tools that the in-process investigator uses, but over MCP
so external clients can reach them: Claude Desktop, Cursor, Cline, Ollama,
n8n, etc. This is the "MCP everywhere" piece of the architecture.

Internal Python callers can keep using `biq.tools.*` directly — no network
hop. The MCP server is for cross-process clients.

Run:
    uv run python -m biq.mcp_servers.bi          # stdio (default)
    uv run mcp dev biq.mcp_servers.bi            # Inspector GUI

Claude Desktop config: see docs/mcp-clients.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from biq import __version__
from biq.tools import causal as causal_tools
from biq.tools import context as ctx_tools
from biq.tools import kg as kg_tools
from biq.tools import kpi as kpi_tools

_REPO_ROOT = Path(__file__).resolve().parents[4]
_KPI_CATALOG = _REPO_ROOT / "docs" / "kpi-catalog.yaml"
_ARCHITECTURE = _REPO_ROOT / "docs" / "architecture.md"

mcp: FastMCP = FastMCP("causal-bi")


# =================================================================
# Tools
# =================================================================


@mcp.tool()
def kpi_query(
    view: str,
    start: str,
    end: str,
    group_by: list[str] | None = None,
) -> dict[str, Any]:
    """Read aggregated KPI data from a governed kpi.* view.

    The kpi.* schema is the semantic layer: agents must read here rather
    than from raw.* directly. Returns up to 200 rows.

    Args:
        view: Name of the kpi.* view. Allowed: conversion_rate_daily,
            aov_daily, gross_margin_weekly, delivery_time_p95,
            review_score_avg, refund_rate, repeat_purchase_rate, churn_30d.
        start: ISO date (inclusive), format YYYY-MM-DD.
        end: ISO date (exclusive), format YYYY-MM-DD.
        group_by: Optional list of extra dimensions to aggregate by, e.g.
            ["device", "channel"]. Numeric columns are summed.
    """
    return kpi_tools.kpi_query(view=view, start=start, end=end, group_by=group_by)


@mcp.tool()
def releases_in_window(start: str, end: str) -> dict[str, Any]:
    """List software releases active during the window [start, end).

    Candidate treatments for causal investigation of KPI moves. A release
    is "active" if it was released before `end` and not rolled back before
    `start`.

    Args:
        start: ISO date (inclusive), format YYYY-MM-DD.
        end: ISO date (exclusive), format YYYY-MM-DD.
    """
    return ctx_tools.releases_in_window(start=start, end=end)


@mcp.tool()
def campaigns_in_window(start: str, end: str) -> dict[str, Any]:
    """List marketing campaigns active during the window [start, end).

    Args:
        start: ISO date (inclusive), format YYYY-MM-DD.
        end: ISO date (exclusive), format YYYY-MM-DD.
    """
    return ctx_tools.campaigns_in_window(start=start, end=end)


@mcp.tool()
def kg_lookup_past_decisions(
    component: str,
    days_back: int = 180,
) -> dict[str, Any]:
    """Look up past insights, decisions, and measured outcomes for a component.

    Use this BEFORE recording a new finding: if the same anomaly happened
    before, you can reference what was tried and whether it worked.

    Args:
        component: e.g. 'mobile_checkout', 'device=mobile', 'paid_search'.
        days_back: window for the lookup, default 180.
    """
    return kg_tools.lookup_past_decisions(component=component, days_back=days_back)


@mcp.tool()
def causal_impact_conversion(
    target_device: str,
    pre_start: str,
    pre_end: str,
    post_start: str,
    post_end: str,
    controls: list[str] | None = None,
) -> dict[str, Any]:
    """Estimate the causal effect of a treatment on a device's conversion rate.

    Uses CausalImpact (Bayesian structural time series) running in the R
    service, with optional synthetic control from other devices.

    Args:
        target_device: 'mobile' | 'desktop' | 'tablet'.
        pre_start: ISO date of pre-period start (inclusive).
        pre_end: ISO date of pre-period end (inclusive).
        post_start: ISO date of post-period start (inclusive).
        post_end: ISO date of post-period end (inclusive).
        controls: Optional list of other devices to use as control series
            (e.g. ["desktop", "tablet"] to estimate a mobile-specific effect).
    """
    return causal_tools.causal_impact_conversion(
        target_device=target_device,
        pre_start=pre_start,
        pre_end=pre_end,
        post_start=post_start,
        post_end=post_end,
        controls=controls,
    )


@mcp.tool()
def evalue(
    rel_effect: float,
    rel_effect_lower: float | None = None,
) -> dict[str, Any]:
    """E-value sensitivity analysis (VanderWeele & Ding 2017).

    Call AFTER causal_impact_conversion when the effect is significant.
    The E-value is the minimum association strength (on the risk-ratio scale)
    that an unmeasured confounder would need to have with both treatment and
    outcome to fully explain the observed effect away. Higher = more robust.

    Args:
        rel_effect: Point estimate as a fractional change (e.g. -0.384 for -38.4 %).
        rel_effect_lower: Optional signed lower 95 % CI bound. Adds an E-value
            for the CI edge closest to the null.
    """
    return causal_tools.evalue(rel_effect=rel_effect, rel_effect_lower=rel_effect_lower)


@mcp.tool()
def power_test(
    p1: float | None = None,
    p2: float | None = None,
    n: int | None = None,
    power: float | None = None,
    sig_level: float = 0.05,
) -> dict[str, Any]:
    """Two-proportion power analysis (two-sided).

    Pass exactly three of {p1, p2, n, power}; the R service solves for the
    fourth. Use this BEFORE causal_impact_conversion when you suspect the
    sample is small — if power < 0.8, an insignificant result is ambiguous
    rather than evidence of no effect.

    Args:
        p1: Baseline proportion in (0, 1).
        p2: Alternative proportion in (0, 1).
        n: Sample size per group.
        power: Desired power in (0, 1). 0.8 is the standard target.
        sig_level: Two-sided alpha, default 0.05.
    """
    return causal_tools.power_test(p1=p1, p2=p2, n=n, power=power, sig_level=sig_level)


# =================================================================
# Resources — read-only context the client can pull into its prompt
# =================================================================


@mcp.resource("kpi://catalog")
def kpi_catalog() -> str:
    """The KPI semantic-layer catalog as YAML.

    Source of truth for KPI definitions: formula, grain, allowed filters,
    owner, freshness SLA, typical misinterpretations.
    """
    return _KPI_CATALOG.read_text()


@mcp.resource("kpi://views")
def kpi_views() -> str:
    """Allowlisted kpi.* view names, one per line."""
    return "\n".join(sorted(kpi_tools.ALLOWED_VIEWS))


@mcp.resource("docs://architecture")
def architecture_doc() -> str:
    """5-layer architecture, MCP topology, end-to-end data flow."""
    return _ARCHITECTURE.read_text()


@mcp.resource("biq://version")
def version() -> str:
    """biq package version."""
    return __version__


if __name__ == "__main__":
    mcp.run()
