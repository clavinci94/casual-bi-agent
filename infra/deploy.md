# Deploying Causal BI Agent

## Stack

| Component | Where | Why |
|---|---|---|
| Postgres + pgvector | **Neon** (managed) | Serverless, Swiss/EU regions, generous free tier |
| FastAPI backend (agents, MCP server, audit) | **Render** web service | Docker, autodeploy from GitHub |
| R Plumber service (CausalImpact) | **Render** private service | Internal HTTP, no public exposure |
| Streamlit HITL UI | **Render** web service | Public, behind auth |
| Next.js dashboard | **Vercel** | Native Next.js host, edge caching, free tier |
| n8n workflow runner | local Docker for now | crons can move to n8n.cloud later |

## One-time setup

### 1. Neon

1. Create an account at <https://neon.tech>, free tier is fine for the demo.
2. Create a project. Region: `Europe (Frankfurt)` keeps data in the EU.
3. In the project, create a database called `causalbi`.
4. Enable extensions: `CREATE EXTENSION IF NOT EXISTS vector;` (Neon supports `pgvector`).
   Apache AGE is **not** currently available on Neon — the relational `kg.*`
   tables in `db/schemas/04_kg.sql` are the fallback used in production.
5. Copy the pooled connection string. Format:
   ```
   postgresql+psycopg://<user>:<password>@<project>-pooler.<region>.aws.neon.tech/causalbi?sslmode=require
   ```

### 2. GitHub

1. Create a new repo (private is fine).
2. Push the local repo: `git remote add origin <url> && git push -u origin main`.

### 3. Render

1. Create an account at <https://render.com>, connect your GitHub.
2. In Render dashboard: **New → Blueprint**, point at the repo. Render reads
   `infra/render.yaml` and creates the three services.
3. Create env-group **biq-secrets**:
   - `DATABASE_URL` = Neon pooled connection string
   - `ANTHROPIC_API_KEY` = your Anthropic key
   - `BIQ_API_KEY` = shared secret for machine callers (n8n, scripts)
   - `BIQ_JWT_JWKS_URL` = `https://<tenant>.eu.auth0.com/.well-known/jwks.json`
   - `BIQ_JWT_ISSUER` = `https://<tenant>.eu.auth0.com/` (trailing slash matters)
   - `BIQ_JWT_AUDIENCE` = `https://api.causal-bi.local` (must match `AUTH0_AUDIENCE` on Vercel)
   - `LANGFUSE_*` if using Langfuse for observability
4. Hit Apply.

### 4. Vercel (Next.js frontend)

1. Account at <https://vercel.com>, connect the same GitHub repo.
2. **Import Project** → pick the repo → Vercel auto-detects Next.js
   under `frontend/`. Set the **Root Directory** to `frontend`.
3. **Environment Variables** (copy from `frontend/.env.local.example`):
   - `NEXT_PUBLIC_API_URL` = `https://biq-api.onrender.com`
   - `AUTH0_SECRET` = `openssl rand -hex 32`
   - `AUTH0_BASE_URL` = the Vercel deployment URL (e.g. `https://causal-bi.vercel.app`)
   - `AUTH0_ISSUER_BASE_URL` = `https://<tenant>.eu.auth0.com`
   - `AUTH0_CLIENT_ID` / `AUTH0_CLIENT_SECRET` = from Auth0 Dashboard
   - `AUTH0_AUDIENCE` = `https://api.causal-bi.local` (same as backend `BIQ_JWT_AUDIENCE`)
   - `AUTH0_SCOPE` = `openid profile email`
4. Hit Deploy.

### 5. Auth0 dashboard (production URLs)

After Vercel gives you the deployment URL (e.g. `https://causal-bi.vercel.app`):

1. <https://manage.auth0.com> → Applications → your app → Settings
2. **Allowed Callback URLs**: add `https://causal-bi.vercel.app/auth/callback`
3. **Allowed Logout URLs**: add `https://causal-bi.vercel.app`
4. **Allowed Web Origins**: add `https://causal-bi.vercel.app`
5. Save.

Both `http://localhost:3000/...` (for dev) and the Vercel URL must be in
the lists at the same time.

## First-time data load

Render builds and deploys, but the DB starts empty. Run these once from your
laptop with the Neon URL in `.env`:

```bash
# Apply schemas
DATABASE_URL=<neon-url> make db-schemas

# Load Olist (CSVs from data/seed/ — same as local)
DATABASE_URL=<neon-url> make db-load

# Simulator
DATABASE_URL=<neon-url> make db-simulate SIM_ARGS="--all"
```

Neon's free tier compute auto-pauses after 5 min idle. First request after
pause has a ~2s cold start.

## Shipping a new release (applying migrations + env updates)

When you push features that need DB migrations or new env vars (this
covers everything from Alembic 0005 onward — Auth0 / system_config /
Shopify columns / outcome-backfill):

```bash
# 1. Apply pending Alembic migrations to Neon.
#    alembic.ini uses relative paths, so run from the backend directory.
cd backend
DATABASE_URL=<neon-url> alembic upgrade head
cd ..

# 2. If env vars changed: edit the Render env group "biq-secrets" in
#    the dashboard, then trigger a Manual Deploy on biq-api so the new
#    values get picked up. Same on Vercel for any AUTH0_* changes.

# 3. Verify the new endpoints.
curl https://biq-api.onrender.com/healthz
curl -H "X-API-Key: $BIQ_API_KEY" https://biq-api.onrender.com/api/settings
```

## Deploy checks

After deploy:

```bash
curl https://biq-api.onrender.com/healthz
curl https://biq-hitl.onrender.com/         # Streamlit HITL UI
```

In Render's logs:
- biq-api: agent runs visible, no DATABASE_URL errors
- biq-r-causal: `Starting server on port 8765`
- biq-hitl: Streamlit serving

## Rollback

Render keeps the last 5 deploys. Rollback in dashboard: **Manual Deploy → previous
commit**.

## Costs (rough, 2026)

- Neon free tier: 0.5 GB storage, 100 hr compute / month — fine for the demo.
- Render Starter: 3 × ~$7/month = $21/month if all on Starter. Free tier
  available for hobbyist projects, but services sleep aggressively.

## Operational notes

- The audit trail in `audit.*` grows with every run. Add a retention job
  (cron in n8n) deleting `audit.agent_steps` older than 90 days when needed.
- R service is stateless; safe to restart anytime.
- The Streamlit HITL UI is a legacy fallback; the Next.js dashboard
  (Vercel) is the primary surface and is gated by Auth0 SSO. Reviewers
  log in with their organisation accounts.
- All side-effect tools are routed through the HITL queue; the LLM cannot
  send email or modify DB state directly.
- n8n crons (daily briefing, outcome measurement) currently run locally.
  When moving them to production, see `n8n/workflows/*.json` — replace
  `host.docker.internal` with `biq-api.onrender.com` and supply
  `X-API-Key` from the `BIQ_API_KEY` secret.
