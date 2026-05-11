"""Smoke test: spawn the MCP server, list tools, call kpi_query with the
mobile_checkout_v2 bug window, verify the mobile conversion drop is visible.

Usage:
    uv run python scripts/mcp_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "biq.mcp_servers.bi"],
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print(f"tools: {tool_names}")
            assert {"kpi_query", "releases_in_window", "campaigns_in_window"} <= set(
                tool_names
            ), f"missing tools: {tool_names}"

            resources = await session.list_resources()
            resource_uris = [str(r.uri) for r in resources.resources]
            print(f"resources: {resource_uris}")

            # KPI catalog reachable
            cat = await session.read_resource("kpi://catalog")  # type: ignore[arg-type]
            assert any("conversion_rate" in c.text for c in cat.contents), (
                "kpi catalog should mention conversion_rate"
            )
            print("kpi://catalog: ok")

            # Call kpi_query for the bug-window slice
            result = await session.call_tool(
                "kpi_query",
                {
                    "view": "conversion_rate_daily",
                    "start": "2018-04-15",
                    "end": "2018-05-10",
                    "group_by": ["device"],
                },
            )
            payload = json.loads(result.content[0].text)
            print(f"kpi_query rows: {payload['row_count']}")

            rows = payload["rows"]
            by_device = {r["device"]: r for r in rows}
            assert "mobile" in by_device, f"no mobile row: {by_device.keys()}"

            mobile = by_device["mobile"]
            cr = mobile["conversions"] / mobile["sessions"] if mobile["sessions"] else 0
            print(
                f"mobile bug-window: {mobile['sessions']} sessions, "
                f"{mobile['conversions']} conversions, conv_rate={cr * 100:.2f}%"
            )
            assert cr < 0.30, f"expected mobile conv < 30% in bug window, got {cr * 100:.2f}%"

            # Call releases_in_window — should find rel_mobile_v2
            rel = await session.call_tool(
                "releases_in_window",
                {"start": "2018-04-15", "end": "2018-05-10"},
            )
            rel_payload = json.loads(rel.content[0].text)
            rel_ids = [r["release_id"] for r in rel_payload["rows"]]
            print(f"active releases: {rel_ids}")
            assert "rel_mobile_v2" in rel_ids, "rel_mobile_v2 should be active in bug window"

    print("\nMCP smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
