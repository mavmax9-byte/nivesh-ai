"""Application configuration.

Settings are loaded from environment variables (and a local .env file in
development). See .env.example at the repository root for the full list of
supported variables.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    APP_NAME: str = "Nivesh AI"
    VERSION: str = "0.1.0"
    ENVIRONMENT: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # API
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]

    # Security (placeholder -- real auth is not implemented in this scaffold)
    SECRET_KEY: str = "change-me-in-production"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://nivesh:nivesh@localhost:5432/nivesh"
    TEST_DATABASE_URL: str = "postgresql+asyncpg://nivesh:nivesh@localhost:5432/nivesh_test"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Knowledge Layer (v0.7) -- embedding generation via OpenAI's API.
    # No other module in this codebase calls an external API requiring a
    # key, so this is the first secret of its kind; None by default so the
    # app/worker still start without it (only knowledge_layer's provider
    # fails, at call time, if it's unset).
    OPENAI_API_KEY: str | None = None
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536

    # ai_agents (v0.9) -- LLM reasoning for the Fundamental Analyst, via
    # OpenAI's chat completions API. Reuses OPENAI_API_KEY above rather
    # than introducing a second secret: one OpenAI account now covers
    # both the embedding calls (knowledge_layer) and this chat-completion
    # call. Low temperature is deliberate -- this is financial analysis,
    # not creative writing, and low temperature reduces run-to-run
    # variance (see ai_agents/providers/openai_provider.py).
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_MAX_OUTPUT_TOKENS: int = 2000
    LLM_TEMPERATURE: float = 0.1

    @property
    def SYNC_DATABASE_URL(self) -> str:
        """Synchronous DSN, used by Alembic which does not run in an event loop."""
        return self.DATABASE_URL.replace("+asyncpg", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
