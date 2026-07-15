"""Runtime configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated service configuration."""

    model_config = SettingsConfigDict(env_prefix="RECALLOPS_", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://recallops:recallops@localhost:5432/recallops"
    )
    analysis_catalog_limit: int = Field(default=1000, ge=1, le=10000)


@lru_cache
def get_settings() -> Settings:
    """Return process-wide settings."""

    return Settings()
