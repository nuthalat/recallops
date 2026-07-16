"""Runtime configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated service configuration."""

    model_config = SettingsConfigDict(env_prefix="INCIDENTECHO_", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://incidentecho:incidentecho@localhost:5432/incidentecho"
    )
    analysis_catalog_limit: int = Field(default=1000, ge=1, le=10000)
    github_incident_label: str = Field(default="incident", min_length=1, max_length=100)
    github_webhook_secret: SecretStr | None = None
    github_app_id: int | None = Field(default=None, ge=1)
    github_app_private_key: SecretStr | None = None
    github_app_private_key_file: Path | None = None

    def github_private_key(self) -> SecretStr | None:
        """Load the App key from exactly one configured secret source."""

        if self.github_app_private_key is not None and self.github_app_private_key_file is not None:
            raise ValueError("configure only one GitHub App private-key source")
        if self.github_app_private_key_file is None:
            return self.github_app_private_key
        return SecretStr(self.github_app_private_key_file.read_text())


@lru_cache
def get_settings() -> Settings:
    """Return process-wide settings."""

    return Settings()
