"""Tests for safe local and live-Azure configuration behavior."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_local_mode_does_not_require_azure_services() -> None:
    settings = Settings(_env_file=None)

    assert settings.azure_enabled is False


def test_live_azure_mode_reports_all_missing_settings() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(azure_enabled=True, _env_file=None)

    message = str(error.value)
    assert "AZURE_ENABLED=true requires" in message
    assert "AZURE_OPENAI_ENDPOINT" in message
    assert "AZURE_OPENAI_CHAT_DEPLOYMENT" in message
    assert "AZURE_OPENAI_EMBEDDING_DEPLOYMENT" in message
    assert "AZURE_SEARCH_ENDPOINT" in message
    assert "AZURE_STORAGE_ACCOUNT_URL" in message


def test_live_azure_mode_accepts_complete_service_configuration() -> None:
    settings = Settings(
        azure_enabled=True,
        azure_openai_endpoint="https://example.openai.azure.com/",
        azure_openai_chat_deployment="chat",
        azure_openai_embedding_deployment="embedding",
        azure_search_endpoint="https://example.search.windows.net",
        azure_storage_account_url="https://example.blob.core.windows.net",
        _env_file=None,
    )

    assert settings.azure_enabled is True
