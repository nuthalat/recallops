"""Runtime configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated service configuration."""

    model_config = SettingsConfigDict(env_prefix="INCIDENTECHO_", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://incidentecho:incidentecho@localhost:5432/incidentecho"
    )
    analysis_catalog_limit: int = Field(default=1000, ge=1, le=10000)
    github_webhook_secret: SecretStr | None = None
    github_app_id: int | None = Field(default=None, ge=1)
    github_app_private_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    """Return process-wide settings."""

    return Settings()
