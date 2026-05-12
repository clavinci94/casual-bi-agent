# Security policy

## Reporting a vulnerability

Email `claudio.vinci@students.fhnw.ch` with the subject `causal-bi: security`.
Do **not** open a public issue.

Include:
- Affected commit SHA or version
- Reproduction steps or PoC
- Impact assessment (what could an attacker do?)
- Suggested fix, if you have one

Expected response: acknowledgement within 5 working days, fix or mitigation
within 30 days for confirmed issues. Embargoed coordinated disclosure if the
issue is severe.

## Threat model (current)

The system is designed for trusted-tenant deployments (one organisation, all
users vetted). The trust assumptions are:

| Component | Trust assumption |
|---|---|
| HTTP API (`/api/*`) | Caller has the `X-API-Key`. Without that, no access. |
| Streamlit HITL UI | Trusted reviewer access. No password gate yet. |
| MCP server (stdio) | Local process invoking it is trusted (Claude Desktop, n8n). |
| R Plumber service | Private — never exposed to public internet (Render `pserv`). |
| Postgres | Behind Neon's auth + IP allowlist. |

## Out of scope (today, on the roadmap)

- SSO / OAuth / SAML for HITL UI and HTTP API
- Per-user roles + row-level security in Postgres
- Rate-limit-aware abuse detection (slowapi gives basic limits today)
- Secrets rotation automation

If your deployment requires any of these, treat the current build as a
pre-production reference implementation, not a hardened SaaS.

## Known weak spots

- `record_finding` and side-effect endpoints are HITL-gated by design; the
  LLM cannot dispatch emails or modify DB state without human approval. But
  the HITL queue itself is currently authenticated only by API key — a leaked
  key is a major incident.
- Audit logs (`audit.*`) are retained forever. Add a cron-based retention job
  before you deploy with personal data.
- The CORS policy in `biq/api/app.py` is wide open (`allow_origins=["*"]`).
  Tighten to your Streamlit/Next.js origins before production.
- The default `BIQ_RATE_LIMIT` is 120 req/min/IP. Tune for your traffic.

## Dependencies

- Python deps: pinned in `backend/uv.lock`. Run `uv lock --upgrade` and review
  carefully when bumping.
- R packages: installed from `rocker/r2u:noble` apt repo. Snapshot-pinned via
  the base image tag.
- Container base images: `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` and
  `rocker/r2u:noble`. Updated quarterly.
