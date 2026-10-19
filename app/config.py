"""Process settings. Secrets come from the environment, never from source."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime knobs. Empty credentials mean the related provider is off."""

    environment: str = "development"
    webhook_signing_secret: SecretStr = SecretStr("local-test-secret")
    event_ttl_seconds: int = 300
    max_request_body_bytes: int = 1_048_576
    company_email_domain: str = "northstar.example"
    company_timezone: str = "America/New_York"

    # Optional model providers. The demo model answers without either key.
    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    llm_fallback_enabled: bool = True
    llm_primary: str = "anthropic"
    llm_fallback: str = "openai"
    llm_timeout_seconds: float = 30.0
    anthropic_model: str = "claude-sonnet-4-20250514"
    openai_model: str = "gpt-4.1-mini"

    bi_api_token: SecretStr = SecretStr("local-bi-token")
    bi_rate_limit_per_minute: int = 60
    bi_query_max_rows: int = 1_000
    bi_query_max_days: int = 366

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def docs_enabled(self) -> bool:
        return self.environment != "production"

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key.get_secret_value())

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings() -> None:
    """Drop the cached settings object. Used by tests."""
    get_settings.cache_clear()
