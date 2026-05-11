# Architecture

## 5-Layer Overview

```
┌──────────────────────────────────────────────────────────────┐
│ 5 · Decision Layer    Next.js + Plotly · R Shiny views       │
│                       HITL queue · Audit trail · Slack alerts│
├──────────────────────────────────────────────────────────────┤
│ 4 · AI Analytics      LangGraph orchestrator                  │
│                       Agents: Data | Stats | Causal |         │
│                               Narrative | Review              │
├──────────────────────────────────────────────────────────────┤
│ 3 · Semantic Layer    kpi.* views (formulas, grain, filters)  │
│                       docs/kpi-catalog.yaml is source-of-truth│
├──────────────────────────────────────────────────────────────┤
│ 2 · Data Platform     Neon Postgres                           │
│                       schemas: raw · kpi · docs · kg · audit  │
│                       extensions: pgvector + Apache AGE       │
├──────────────────────────────────────────────────────────────┤
│ 1 · Data Sources      Olist CSVs · simulated events,          │
│                       campaigns, releases, support tickets    │
│                       (later: Shopify/Stripe/GA via n8n)      │
└──────────────────────────────────────────────────────────────┘
```

## MCP Topology

All tools are MCP servers; LangGraph agents are the only callers.

```
                    ┌──────────────────┐
                    │   Orchestrator   │
                    └──────────┬───────┘
                               │
       ┌───────────┬───────────┼───────────┬────────────┐
       ↓           ↓           ↓           ↓            ↓
   Data Agent  Stats Agent  Causal Agent  Narrative   Review
       │           │           │           │            │
   ────┴───────────┴───────────┴───────────┴────────────┴────  MCP bus
       │           │           │           │            │
   SQL-MCP     Python-MCP  R-MCP         KG-MCP     n8n-MCP
   (kpi views) (DoWhy,     (CausalImpact,(graph     (webhooks,
                EconML,    MatchIt,      queries,    Slack,
                forecast)  dagitty)      decisions)  email,
                                                     schedule)
```

## Data flow: anomaly investigation (end-to-end)

1. **n8n** cron triggers `kpi-anomaly-scan` every hour.
2. **Anomaly detector** queries `kpi.conversion_rate_daily` via SQL-MCP.
3. Anomaly detected → **Orchestrator** starts a run, logs to `audit.agent_runs`.
4. **Data Agent** slices the drop by device, region, channel, category.
5. **Causal Agent** identifies candidate treatments (`raw.campaigns`, `raw.releases`) and runs R `CausalImpact` via R-MCP.
6. **Narrative Agent** drafts a management note in Markdown.
7. **Review Agent** verifies: KPI definitions match the catalog, all sources cited, confidence within bounds, no PII leaked.
8. Result lands in the **HITL queue**; Slack notification sent via n8n-MCP.
9. Approver clicks ✓ or ✗ in the UI → row in `audit.hitl_decisions`, `kg.Decision` node created.
10. After the observation window, the actual outcome is measured and written to `audit.outcomes` and `kg.Outcome` — **closes the learning loop**.

## Schemas at a glance

See `db/schemas/*.sql` for full DDL.

| Schema | Purpose | Key tables |
|---|---|---|
| `raw` | Operational data (append-only where possible) | `customers`, `orders`, `order_items`, `products`, `payments`, `reviews`, `sellers`, `web_events`, `campaigns`, `releases`, `support_tickets` |
| `kpi` | Semantic layer (views / materialised views) | `conversion_rate_daily`, `gross_margin_weekly`, `churn_30d`, `aov_daily`, `delivery_time_p95`, ... |
| `docs` | Unstructured + vectors | `documents`, `chunks` (with `vector(1536)`) |
| `kg` | Knowledge graph | `nodes`, `edges` (or AGE labels: `Customer`, `Insight`, `Decision`, `Outcome`, ...) |
| `audit` | Full observability | `agent_runs`, `agent_steps`, `tool_calls`, `sources_used`, `recommendations`, `hitl_decisions`, `outcomes` |

## Why this shape

- **One DB, many schemas**: cheaper to deploy, one backup, one connection pool, one place to audit. Splitting only makes sense at >100GB or >1k QPS — neither applies for years.
- **Semantic layer is enforced by access pattern, not by hope**: agents have a SQL-MCP tool that only exposes `kpi.*`. They cannot reach `raw.*` even if they tried.
- **MCP between agents and tools**: replace the LLM tomorrow (Claude → GPT → Ollama) without touching tools. Replace a tool (Python → Rust) without touching agents.
- **Audit-as-data**: every step is a row. That row can be queried, charted, alerted on. Trust is a SELECT statement.
