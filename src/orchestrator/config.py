"""Central configuration loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM providers
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_model: str = "claude-opus-4-8"
    default_llm_provider: str = "mock"  # openai | anthropic | mock

    # LLM safety limits
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    max_task_chars: int = 8000

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "orchestrator"
    postgres_user: str = "orchestrator"
    postgres_password: str = "orchestrator"

    # ChromaDB
    chroma_host: str = "localhost"
    chroma_port: int = 8000

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Human-in-the-loop thresholds
    confidence_threshold: float = 0.6
    quality_threshold: float = 0.6
    max_retries: int = 2

    # Review-UI authentication (VA-01)
    # Secure by default. Set REVIEW_AUTH_ENABLED=false ONLY for local demos.
    review_auth_enabled: bool = True
    # Comma-separated "name:token" pairs, e.g. "alice:s3cret,bob:hunter2".
    review_users: str = ""

    # Observability
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "multi-agent-orchestrator"

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def active_provider(self) -> str:
        """Resolve the provider, downgrading to mock when no key is present."""
        if self.default_llm_provider == "openai" and self.openai_api_key:
            return "openai"
        if self.default_llm_provider == "anthropic" and self.anthropic_api_key:
            return "anthropic"
        return "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
