# n8n workflows

Importable n8n workflow exports that exercise the public Causal BI HTTP API.
n8n is the "operational integration" layer — it triggers agents on schedules
or external events and routes findings to humans (Slack, email, Teams) or
other systems (ticketing, BI tools, dashboards).

## Workflows

### `monday-briefing.json` — Weekly anomaly scan

Cron-triggered every Monday at 08:00. Calls `POST /api/investigations/anomaly`,
filters the response for high-severity insights, posts a digest to Slack.

```
[Cron Mon 08:00] → [HTTP: POST /api/investigations/anomaly]
                       → [IF severity=high in any insight?]
                            → [HTTP: Slack webhook with summary]
                            → (else: noop)
```

### `daily-briefing.json` — Daily Tagesbriefing at 07:00

Cron-triggered Mon–Fri at 07:00 Europe/Zurich. Forces a fresh briefing
(`POST /api/briefing/refresh`) so the first user of the day reads from
the warm cache instead of paying the 20 s synthesis latency. If the
briefing contains any `urgency: high` signal, Slack receives the
headline + each urgent bullet's *what / why / action*. On any HTTP
failure (3 retries, 30 s apart) Slack receives an error alert.

```
[Cron Mon–Fri 07:00 Europe/Zurich]
    → [HTTP: POST /api/briefing/refresh]      (3× retry on 5xx)
        ├─ success → [IF any signal urgency=high?]
        │              ├─ yes → [Slack: headline + urgent bullets]
        │              └─ no  → (noop)
        └─ error   → [Slack: error alert with details]
```

Extra env var beyond the shared ones:

- `DASHBOARD_PUBLIC_URL` — used in Slack messages to deep-link to the
  Markt-Radar page (e.g. `https://app.causal-bi.ch`).

## Setup

In n8n (self-hosted via Render, or n8n.cloud):

1. **Import** the JSON: *Workflows → Import from File*.
2. Set the workflow's env vars:
   - `BIQ_API_URL` — e.g. `https://biq-api.onrender.com`
   - `BIQ_API_KEY` — the value matching the API's `BIQ_API_KEY`
   - `SLACK_WEBHOOK_URL` — incoming webhook URL from Slack
   - `HITL_URL` — e.g. `https://biq-hitl.onrender.com` (monday-briefing)
   - `DASHBOARD_PUBLIC_URL` — e.g. `https://app.causal-bi.ch` (daily-briefing)
3. **Activate** the workflow.

## Adding more workflows

Patterns that fit nicely:

- **Outcome closer** (cron, weekly): for every `audit.recommendations` with
  status=approved older than 7 days, recompute the affected KPI for the
  observation window and `POST /api/kg/outcomes` to close the learning loop.
- **Anomaly → Jira** (webhook): on high-severity finding, open a Jira ticket
  with the investigation trace.
- **Causal-on-demand** (webhook from Slack slash command): `/causal mobile
  2018-04-15 2018-05-10` triggers `POST /api/investigations/graph` and
  posts the result back as a thread reply.

For all of these the only n8n-internal config you need is the API key — the
HTTP API does the heavy lifting.
