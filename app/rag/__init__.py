"""Minimal, inspectable retrieval-augmented generation components."""

from collections.abc import Callable
from functools import lru_cache
from inspect import signature
from typing import cast

from azure.identity import DefaultAzureCredential

from app.config import get_settings
from app.rag.azure import AzureOpenAIAdapter, AzureSearchAdapter
from app.rag.models import ChatResult, Citation, IndexedDocument, RagAnswer, RetrievedChunk
from app.rag.service import RagService


def _build_improved_service(
    openai: AzureOpenAIAdapter,
    search: AzureSearchAdapter,
) -> RagService:
    """Build the improved service with optional analyzer-constructor support."""

    analyzer = openai.query_analyzer()
    parameters = signature(RagService.__init__).parameters
    analyzer_name = next(
        (name for name in ("query_analyzer", "analyzer") if name in parameters),
        None,
    )
    constructor = cast(Callable[..., RagService], RagService)
    if analyzer_name is None:
        return constructor(openai, search, openai)
    return constructor(openai, search, openai, **{analyzer_name: analyzer})


@lru_cache
def get_rag_service() -> RagService:
    """Build one Entra-authenticated RAG service lazily per application process."""

    settings = get_settings()
    if not settings.azure_enabled:
        raise RuntimeError("Set AZURE_ENABLED=true before using the chat endpoint")
    credential = DefaultAzureCredential()
    openai = AzureOpenAIAdapter.from_settings(settings, credential)
    search = AzureSearchAdapter.from_settings(settings, credential)
    return _build_improved_service(openai, search)


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
