"""Public factory for the frozen vector-only baseline runtime."""

from functools import lru_cache

from azure.identity import DefaultAzureCredential

from app.baseline.models import BASELINE_TOP_K
from app.baseline.search import AzureBaselineSearch
from app.baseline.service import BaselineService
from app.config import get_settings
from app.rag.azure import AzureOpenAIAdapter


@lru_cache
def get_baseline_service() -> BaselineService:
    """Build one Entra-authenticated baseline service per process."""

    settings = get_settings()
    if not settings.azure_enabled:
        raise RuntimeError("Set AZURE_ENABLED=true before using the baseline service")
    credential = DefaultAzureCredential()
    openai = AzureOpenAIAdapter.from_settings(settings, credential)
    search = AzureBaselineSearch.from_settings(settings, credential)
    return BaselineService(openai, search, openai)


build_baseline_service = get_baseline_service

__all__ = [
    "BASELINE_TOP_K",
    "AzureBaselineSearch",
    "BaselineService",
    "build_baseline_service",
    "get_baseline_service",
]
