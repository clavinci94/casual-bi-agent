# Connecting MCP clients

The `causal-bi` MCP server exposes the same tools the in-process investigator uses
(`kpi_query`, `releases_in_window`, `campaigns_in_window`) plus a few resources
(`kpi://catalog`, `kpi://views`, `docs://architecture`, `biq://version`).

Internal Python code keeps calling `biq.tools.*` directly — no network hop. MCP is
for external clients.

## Prerequisites

- Local Postgres running (`make db-up && make db-seed`)
- `uv` available in `PATH`
- `DATABASE_URL` reachable by the MCP server process

## Quick test: MCP Inspector

```bash
make mcp-inspect
```

Opens the Inspector GUI in your browser. List tools, list resources, call
`kpi_query` interactively, watch tool calls live.

## Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "causal-bi": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/claudio/causal-bi/backend",
        "run",
        "python",
        "-m",
        "biq.mcp_servers.bi"
      ],
      "env": {
        "DATABASE_URL": "postgresql+psycopg://causalbi:causalbi@localhost:5433/causalbi"
      }
    }
  }
}
```

Restart Claude Desktop. The `causal-bi` server appears in the tool menu. Ask
*"using causal-bi, why did mobile conversion fall in early May 2018?"* — Claude
will call `kpi_query` and `releases_in_window` against your local Postgres.

## Cursor

Edit `~/.cursor/mcp.json` (or workspace `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "causal-bi": {
      "command": "uv",
      "args": ["--directory", "/Users/claudio/causal-bi/backend", "run", "python", "-m", "biq.mcp_servers.bi"]
    }
  }
}
```

## Cline (VS Code)

Add to Cline settings:

```json
{
  "causal-bi": {
    "command": "uv",
    "args": ["--directory", "/Users/claudio/causal-bi/backend", "run", "python", "-m", "biq.mcp_servers.bi"]
  }
}
```

## n8n

The n8n MCP node (community node `n8n-nodes-mcp`) accepts stdio servers. Same
command as above. Loop it into a "BI investigator" workflow that triggers on a
Slack message or schedule.

## Ollama (local LLMs)

Ollama doesn't natively speak MCP yet, but `ollama-mcp-bridge` and similar
proxies do. The bridge speaks MCP to our server and exposes the tools via
Ollama's function-calling API.

## Adding a new tool

1. Add the Python function to `backend/src/biq/tools/` (single source of truth).
2. Decorate a thin wrapper in `backend/src/biq/mcp_servers/bi.py` with `@mcp.tool()`.
3. Update the in-process investigator's tool definitions in
   `backend/src/biq/agents/investigator.py` so they stay in sync.
4. Document any new MCP-only tool here.

## What is NOT exposed via MCP

- `record_finding`: writes to `audit.recommendations`. Side-effects belong to the
  in-process orchestrator with full audit context, not external clients. If you
  want clients to submit findings, add a dedicated `/submit` endpoint with auth.
- Direct `raw.*` access. The semantic layer (`kpi.*`) is the only read path.
- Audit-log access. The agent logs to it; readers go through Langfuse or a
  separate dashboard.
