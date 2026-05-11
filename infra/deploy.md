# Deploying Causal BI Agent

## Stack

| Component | Where | Why |
|---|---|---|
| Postgres + pgvector | **Neon** (managed) | Serverless, Swiss/EU regions, generous free tier |
| FastAPI backend (agents, MCP server, audit) | **Render** web service | Docker, autodeploy from GitHub |
| R Plumber service (CausalImpact) | **Render** private service | Internal HTTP, no public exposure |
| Streamlit HITL UI | **Render** web service | Public, behind auth |
| n8n workflow runner | **Render** web service (optional) | Cron + integrations |

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
   - `LANGFUSE_*` if using Langfuse for observability
4. Hit Apply.

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
- HITL UI sessions are non-persistent (Streamlit). Reviewer name is just a
  text field today — add SSO before exposing to real users.
- All side-effect tools are routed through the HITL queue; the LLM cannot
  send email or modify DB state directly.
