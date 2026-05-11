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
- [ ] KPI catalog → view generator (`kpi.*`)
- [ ] Olist seed loader + simulators (web_events, campaigns, releases, support_tickets)
- [ ] First MCP server: SQL tool against `kpi.*`
- [ ] First agent: anomaly detector
- [ ] First causal demo: `CausalImpact` on a known simulated treatment
- [ ] Multi-agent orchestration (LangGraph)
- [ ] HITL UI
- [ ] Eval harness
- [ ] Deploy to Render + Neon

## Licence

TBD.
