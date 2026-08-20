"""Typed application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with safe, non-secret defaults."""

    app_env: str = "development"
    log_level: str = "INFO"
    azure_enabled: bool = False
    azure_auth_mode: Literal["entra", "api_key"] = "entra"

    azure_openai_endpoint: str | None = None
    azure_openai_chat_deployment: str | None = None
    azure_openai_embedding_deployment: str | None = None

    azure_search_endpoint: str | None = None
    azure_search_baseline_index: str = "enterprise-kb-baseline-v1"
    azure_search_improved_index: str = "enterprise-kb-improved-v1"

    azure_storage_account_url: str | None = None
    azure_storage_container: str = "knowledge-base"
    applicationinsights_connection_string: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_live_azure_configuration(self) -> Self:
        """Fail early when live Azure mode lacks required service settings."""

        if not self.azure_enabled:
            return self

        required = {
            "AZURE_OPENAI_ENDPOINT": self.azure_openai_endpoint,
            "AZURE_OPENAI_CHAT_DEPLOYMENT": self.azure_openai_chat_deployment,
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": self.azure_openai_embedding_deployment,
            "AZURE_SEARCH_ENDPOINT": self.azure_search_endpoint,
            "AZURE_STORAGE_ACCOUNT_URL": self.azure_storage_account_url,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"AZURE_ENABLED=true requires: {joined}")

        return self


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-by-convention settings instance per process."""

    return Settings()
