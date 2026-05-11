# Causal BI Agent

> Agentic Business Intelligence that explains **why**, not just **what** — with causal inference, organisational memory, and human-in-the-loop action.

## The pitch

Classic BI tools (Power BI, Tableau) show numbers. Modern "AI BI" tools (Hex Magic, Snowflake Cortex Analyst) answer text-to-SQL questions. Both leave the **why** to the analyst.

This platform:

1. **Monitors KPIs proactively** — notices anomalies without being asked.
2. **Runs causal inference** — separates correlation from causation using R (`CausalImpact`, `MatchIt`, `dagitty`) and Python (`DoWhy`, `EconML`).
3. **Drafts actionable recommendations** — and routes them through human-in-the-loop approval.
4. **Remembers what worked** — every decision and its outcome flow into a knowledge graph, so the system gets smarter about *your* business over time.

## Stack

Neon Postgres (Apache AGE + pgvector) · Python (FastAPI, LangGraph) · R (Plumber) · MCP everywhere · n8n · Next.js · R Shiny. Deploy: Render + Neon + Vercel.

## Status

Pre-MVP. Schema design in progress.

## For contributors and AI assistants

Read [`AGENTS.md`](AGENTS.md) before doing anything.

## Roadmap

- [x] Repo scaffold + AGENTS.md
- [x] DB schema v0 (raw + docs + kg + audit)
- [x] Local dev: docker-compose Postgres+pgvector, backend skeleton, Makefile
- [x] Olist seed loader
- [x] Simulators: `web_events` / `campaigns` / `releases` / `support_tickets` (with deliberate `mobile_checkout_v2` anomaly for the causal demo)
- [x] KPI views (`02_kpi.sql`): 7 working + `churn_30d` placeholder
- [x] Audit logging module (`audit.*` writes)
- [x] First agent: heuristic anomaly detector — finds the simulated mobile bug
- [x] LLM-driven investigator agent (Claude tool-use, prompt-cached, fully audited)
- [x] MCP server (`causal-bi`): tools + resources exposed for Claude Desktop / Cursor / n8n / Ollama
- [x] R + `CausalImpact` service (Plumber in Docker, port 8765); Python tool + MCP exposure; smoke-tested against the simulated mobile_v2 ground truth
- [ ] LangGraph multi-agent orchestration (Orchestrator → Data → Causal → Narrative → Review)
- [ ] First causal demo: `CausalImpact` on the rediscovered mobile_checkout_v2 treatment
- [ ] Multi-agent orchestration
- [ ] HITL UI
- [ ] Eval harness
- [ ] Deploy to Render + Neon

## Local quickstart

```bash
cp .env.example .env
make db-up && make backend-sync
# download Olist into data/seed/ (see data/seed/README.md)
make db-seed              # schemas + Olist load + simulated extensions
make detect-anomalies DETECT_ARGS="--date 2018-05-05"
# expected: mobile conversion drop flagged as 'high' severity

# LLM-driven investigator (needs ANTHROPIC_API_KEY in .env)
make investigate Q="What happened to mobile conversion rate in early May 2018?"
```

## Licence

TBD.
