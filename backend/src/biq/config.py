from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = parent of `backend/` = parent.parent.parent.parent from this file
# (config.py -> biq -> src -> backend -> repo root).
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _REPO_ROOT / "backend" / ".env"),
        extra="ignore",
    )

    database_url: str
    app_env: str = "local"
    log_level: str = "info"
    simulation_seed: int = 42
    brl_to_chf: float = 0.16

    anthropic_api_key: str | None = None
    # Admin API key for /v1/organizations/* — separate from anthropic_api_key.
    # Issued in the Claude Console (Organization Settings → Admin Keys) and
    # has read access to org-level resources (API keys, workspaces, members).
    anthropic_admin_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # External-intelligence providers. Each is independently optional —
    # tools degrade gracefully when a key is missing (return an empty
    # result with an explanation, rather than crashing the agent loop).
    tavily_api_key: str | None = None
    newsapi_key: str | None = None
    alpha_vantage_key: str | None = None

    # Shopify ETL source. See docs/shopify-setup.md for how to create the
    # private app and where to copy the Admin API token. Both must be set
    # for `make shopify-sync` to do anything.
    shopify_shop_domain: str | None = None  # e.g. "causal-bi-demo.myshopify.com"
    shopify_admin_api_token: str | None = None  # shpat_...
    shopify_api_version: str = "2025-01"

    # Auth mode for /api/* — gates how the FastAPI layer authenticates
    # callers. See docs/sso-setup.md for the SSO flow.
    #   "api_key" (default)  — X-API-Key header against BIQ_API_KEY
    #   "bearer_jwt"          — Authorization: Bearer <jwt>, validated
    #                           via JWKS at BIQ_JWT_JWKS_URL
    #   "disabled"            — no auth (only for local dev)
    biq_auth_mode: str = "api_key"
    biq_jwt_jwks_url: str | None = None  # e.g. https://<tenant>.auth0.com/.well-known/jwks.json
    biq_jwt_issuer: str | None = None  # e.g. https://<tenant>.auth0.com/
    biq_jwt_audience: str | None = None  # API identifier registered with the IdP

    # When set, the HTTP API requires X-API-Key: <value> on /api/*.
    # Unset = open (dev mode).
    biq_api_key: str | None = None

    # Which slice of raw.shopify_* the KPI views (and therefore the
    # Markt-Radar + Briefing-Agent) read from. The migration tags every
    # row with data_source = 'sim' | 'live'. KPI views filter via the
    # Postgres session variable `biq.data_source`, which biq.db sets
    # from this value when each connection is checked out.
    #   "sim"   — read the simulated demo store (default — safe for fresh installs)
    #   "live"  — read the real Shopify dev-store synced via shopify-sync
    biq_data_source: str = "sim"

    # Multi-agent run budgets. Hard caps that short-circuit the supervisor
    # to the reporter when exceeded — protects against runaway investigations
    # blowing up cost per tenant. Tuned for Sonnet 4.6 + the current 5-lead
    # plan: a normal run lands around 5k tokens / $0.05, so the defaults
    # leave 20x headroom for retries before tripping.
    biq_max_tokens_per_run: int = 100_000
    biq_max_cost_usd_per_run: float = 2.0


settings = Settings()  # type: ignore[call-arg]
