# AGENTS.md

Operational guidance for AI coding assistants working in this repo. Read this first — everything else flows from it.

## What this is

**Causal BI Agent** — an agentic business intelligence platform that goes beyond text-to-SQL and RAG: it monitors KPIs proactively, runs causal inference on anomalies, drafts actionable recommendations with human-in-the-loop approval, and builds organisational memory in a knowledge graph.

Started as a portfolio project for a Business Intelligence Bachelor at a Swiss university. Architecture is built so it can grow into a real SaaS product without rewrites.

## Domain

E-commerce. Primary dataset: [Olist Brazilian E-Commerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (~100k orders, 9 tables, free), extended with simulated `web_events`, `campaigns`, `releases`, and `support_tickets`. Olist has no clickstream and no treatments — and without treatments you cannot demonstrate causal inference, which is the differentiator.

## Tech stack

- **DB**: Neon Postgres 16. Single database, multiple schemas (`raw`, `kpi`, `docs`, `kg`, `audit`). Extensions: `pgvector` (confirmed on Neon), Apache `age` for the knowledge graph if available — otherwise relational adjacency fallback (see `db/schemas/04_kg.sql`).
- **Backend**: Python 3.12, FastAPI, LangGraph for agent orchestration, SQLAlchemy + Alembic.
- **MCP everywhere**: every capability — SQL query, graph query, Python compute, R statistics, n8n trigger — is an MCP server. LLM is pluggable.
- **R**: via Plumber, exposed as an MCP server. Used for causal inference (`CausalImpact`, `MatchIt`, `dagitty`) and statistical rigor.
- **Workflow & integration**: n8n self-hosted on Render. Handles ETL from external APIs, scheduling, webhooks.
- **Frontend**: Next.js + Plotly (main dashboard) and R Shiny (specialised statistical views). Not built yet — backend first.
- **Eval & observability**: Langfuse for traces, custom eval harness for regression tests.
- **Deploy**: Render (backend + n8n) + Neon (DB) + Vercel (frontend, later). GitHub Actions for CI.

## Repo layout

```
causal-bi/
├── AGENTS.md           ← you are here
├── README.md
├── docs/
│   ├── architecture.md     5-layer architecture, MCP topology, data flow
│   ├── kpi-catalog.yaml    semantic layer — source of truth for KPI definitions
│   └── decisions/          ADRs (architecture decision records)
├── backend/                FastAPI + LangGraph + MCP servers (TBD)
├── db/
│   └── schemas/            SQL DDL per logical schema
├── data/
│   ├── seed/               Olist CSVs (gitignored) + simulators
│   └── notebooks/          exploration
├── n8n/
│   └── workflows/          exported n8n flow JSONs
└── infra/                  Render + Neon configs
```

## Architecture in one paragraph

Five logical layers, all in one Postgres DB: `raw` (Olist + simulated ops data), `kpi` (semantic views generated from `docs/kpi-catalog.yaml`), `docs` (Markdown notes + `pgvector` chunks), `kg` (knowledge graph of entities, decisions, outcomes), `audit` (every agent step). Agents are LangGraph nodes (Orchestrator → Data, Stats, Causal, Narrative, Review). Every tool the agents touch is an MCP server. n8n handles scheduling and external integration. Decisions and their outcomes flow back into the KG — the system learns from itself.

See `docs/architecture.md` for the full picture.

## Setup

TBD once backend exists. Provisional:

```bash
# 1. Postgres (Neon or local)
psql $DATABASE_URL -f db/schemas/01_raw.sql
psql $DATABASE_URL -f db/schemas/03_docs.sql
psql $DATABASE_URL -f db/schemas/04_kg.sql
psql $DATABASE_URL -f db/schemas/05_audit.sql

# 2. Seed data
# Download Olist CSVs into data/seed/ — see data/seed/README.md

# 3. Backend (not built yet)
# cd backend && uv sync && uv run uvicorn biq.api.app:app --reload
```

## Conventions

- **Python**: `ruff` for lint + format, `mypy` strict where feasible.
- **SQL**: `lower_snake_case` everywhere. Schema-qualified table names always (`raw.orders`, never bare `orders`).
- **KPIs**: agents must only read from `kpi.*` views, never `raw.*` directly. The semantic layer is the governance guarantee — non-negotiable.
- **MCP tools**: every tool has explicit input/output JSON schemas, an allowlist for parameters, and an audit-log entry path.
- **Secrets**: `.env` only, never committed. `.env.example` is the contract.
- **Migrations**: Alembic. Never edit committed migrations; create new ones.
- **Commits**: Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`).

## Key decisions (and what we rejected)

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Single DB vs multi-DB | Single Neon Postgres with schemas | Separate Neo4j + Postgres + Pinecone | Cost, deploy simplicity, one source of truth |
| Graph store | Apache AGE in Postgres (fallback: relational adjacency) | External Neo4j AuraDB | Same DB, same backups, one connection |
| Agent framework | LangGraph | CrewAI, AutoGen | Best state management, HITL support, debuggable traces |
| Domain | E-commerce (Olist) | SaaS metrics, Trade | Best free dataset, strongest causal story |
| LLM | Pluggable via MCP, default Claude Sonnet | Hardcoded OpenAI | No lock-in; local Ollama for sensitive prompts |
| Causal toolkit | Both Python (DoWhy, EconML) AND R (CausalImpact, MatchIt, dagitty) | Python only | R has the most mature causal toolbox; differentiator |
| Frontend | Next.js + Shiny dual | Pure Shiny | Next.js for hiring optics + Plotly; Shiny for statistical demos |

## What NOT to do

- **Do not** let agents write raw SQL against `raw.*`. Use `kpi.*` views or MCP tools. The semantic layer is non-negotiable.
- **Do not** bypass the HITL queue for any action with external side effects (emails, payments, status changes). Read-only actions are fine.
- **Do not** add a new MCP tool without an input/output schema, a test, and an audit-log entry path.
- **Do not** put credentials in code or test fixtures. `.env` and `.env.example` only.
- **Do not** add backwards-compat shims for old schemas during pre-MVP. Rewrite, don't patch.
- **Do not** create new top-level dirs without updating this file.

## Context an agent needs to know

- **Course context**: this also serves as the deliverable for a BI Bachelor module. The 14 exercises in `docs/course-mapping.md` (TBD) map to features of this system — when adding a feature, check if it also satisfies an exercise so we get double-value.
- **Currency**: CHF in UI (Swiss audience), but Olist source data is BRL. Convert at ingest with a fixed rate constant; document the rate and date in an ADR.
- **"Causal" is the differentiator**: when in doubt about what feature to build, ask: does this strengthen the causal-reasoning story? If yes, prioritise.
- **The audit trail is product, not afterthought**: every recommendation must trace back to its inputs. Don't shortcut this — it's what makes the system trustworthy enough to deploy in a real company.

## Status

Pre-MVP. Repo scaffold + DB schema v0 exist. Backend not started. See `README.md` Roadmap.
