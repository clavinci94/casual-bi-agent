# Clean architecture mapping

The repo follows a Clean / Hexagonal Architecture: domain logic in the centre,
infrastructure at the edges, every dependency points inward.

```
            ┌──────────────────────────────────────────────────┐
            │                Interface adapters                │
            │  ┌────────┐  ┌─────────┐  ┌────────┐  ┌────────┐ │
            │  │ FastAPI│  │   MCP   │  │Streamlit│ │   CLI   │ │
            │  │ (TBD)  │  │ servers │  │  hitl   │ │ scripts │ │
            │  └───┬────┘  └────┬────┘  └────┬────┘ └────┬────┘ │
            └──────┼─────────────┼───────────┼───────────┼──────┘
                   │             │           │           │
                   ▼             ▼           ▼           ▼
            ┌──────────────────────────────────────────────────┐
            │                 Application layer                │
            │     biq/agents/{anomaly, investigator, graph}    │
            │  Orchestrates tools to fulfil a use case;        │
            │  manages run lifecycle + audit                   │
            └──────────────────┬───────────────────────────────┘
                               │
                               ▼
            ┌──────────────────────────────────────────────────┐
            │                  Domain layer                    │
            │            biq/tools/{kpi, context, causal}      │
            │  Pure operations over the governed semantic      │
            │  layer. No knowledge of how they are invoked.    │
            └────────────┬─────────────────┬───────────────────┘
                         │                 │
                         ▼                 ▼
            ┌──────────────────────┐ ┌────────────────────────┐
            │  Infrastructure: DB  │ │ Infrastructure: R svc  │
            │  biq/db.py + audit   │ │ httpx → Plumber        │
            │  + Postgres schemas  │ │ (CausalImpact)         │
            └──────────────────────┘ └────────────────────────┘
```

## Layer responsibilities

### Domain (`biq/tools/`, `biq/seeders/`)
- **`tools/kpi.py`** — read from the governed `kpi.*` views; allowlist enforces
  what views are reachable.
- **`tools/context.py`** — read from `raw.releases` and `raw.campaigns`.
- **`tools/causal.py`** — wraps the R Plumber endpoint; converts between
  pandas time series and the wire format.
- **`seeders/synthetic.py`** — pure data generators with a fixed seed.

These modules know about the DB schema and Postgres, but **not** about agents,
LLMs, MCP, HTTP, or UI. They never call `audit.*` — auditing is the application
layer's responsibility.

### Application (`biq/agents/`, `biq/audit.py`)
- **`agents/anomaly.py`** — heuristic detector; rule-based; writes audit.
- **`agents/investigator.py`** — LLM-driven loop using Claude tool-use.
- **`agents/graph.py`** — LangGraph multi-agent with explicit review gate.
- **`audit.py`** — cross-cutting concern: every agent run is logged here.

Agents compose tools to solve a use case. They are the only place where
`audit.*` is written. They have no knowledge of which interface invoked them.

### Interface adapters (`biq/mcp_servers/`, `biq/ui/`, `backend/scripts/`, `biq/api/`)
- **MCP servers** — thin wrappers that expose tools to external clients.
- **Streamlit HITL** — review queue UI.
- **CLI scripts** — local entry points.
- **FastAPI** (TBD) — HTTP entry point for production.

Adapters translate between the outside world and the application layer. They
own no business logic.

### Infrastructure (`db/schemas/`, `r-service/`, `docker-compose.yml`, `infra/`)
- Postgres schemas: `raw` (data sources), `kpi` (semantic layer), `docs`
  (vectors), `kg` (knowledge graph), `audit` (observability).
- R Plumber service: stateless CausalImpact endpoint.
- Docker compose: local dev stack.
- Render blueprint: production deploy.

## Why this matters

- **Replaceability**: swap Claude for Ollama (interface adapter change only);
  swap Postgres for SQL Server (infrastructure change only); add a new
  Slack-based interface without touching tools or agents.
- **Testability**: domain and application layers can be unit-tested without
  spinning up the LLM, MCP, or UI. Coverage > 88% is achieved by testing
  only these two layers.
- **Governance**: tools can only read from `kpi.*` views, never `raw.*`.
  Side-effect tools (record_finding, future email/ticket dispatch) live in
  the application layer where the audit context is available.

## Module dependency rules (enforced by convention, not yet by linter)

| From → To | Allowed? |
|---|---|
| Domain → Infrastructure | Yes |
| Application → Domain | Yes |
| Application → Infrastructure (audit only) | Yes |
| Interface → Application | Yes |
| Interface → Domain | Yes (read-only tools) |
| Domain → Application | **No** |
| Domain → Interface | **No** |
| Infrastructure → anything else | **No** |

If you find yourself wanting to import `biq.agents` from `biq.tools`, that's a
signal the abstraction is wrong — extract the orchestration concern into a
new application-layer function instead.
