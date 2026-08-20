"""Minimal, inspectable retrieval-augmented generation components."""

from functools import lru_cache

from azure.identity import DefaultAzureCredential

from app.config import get_settings
from app.rag.azure import AzureOpenAIAdapter, AzureSearchAdapter
from app.rag.models import ChatResult, Citation, IndexedDocument, RagAnswer, RetrievedChunk
from app.rag.service import RagService


@lru_cache
def get_rag_service() -> RagService:
    """Build one Entra-authenticated RAG service lazily per application process."""

    settings = get_settings()
    if not settings.azure_enabled:
        raise RuntimeError("Set AZURE_ENABLED=true before using the chat endpoint")
    credential = DefaultAzureCredential()
    openai = AzureOpenAIAdapter.from_settings(settings, credential)
    search = AzureSearchAdapter.from_settings(settings, credential)
    return RagService(openai, search, openai)


build_chat_service = get_rag_service

__all__ = [
    "ChatResult",
    "Citation",
    "IndexedDocument",
    "RagAnswer",
    "RagService",
    "RetrievedChunk",
    "build_chat_service",
    "get_rag_service",
]
