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
from biq.tools import context as ctx_tools
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
