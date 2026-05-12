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

    # When set, the HTTP API requires X-API-Key: <value> on /api/*.
    # Unset = open (dev mode).
    biq_api_key: str | None = None


settings = Settings()  # type: ignore[call-arg]
