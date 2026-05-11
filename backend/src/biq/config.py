from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        extra="ignore",
    )

    database_url: str
    app_env: str = "local"
    log_level: str = "info"
    simulation_seed: int = 42
    brl_to_chf: float = 0.16

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"


settings = Settings()  # type: ignore[call-arg]
