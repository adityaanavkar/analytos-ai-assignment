"""Mocked tests for direct Azure SDK adapters."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from app.rag.azure import AzureOpenAIAdapter, AzureSearchAdapter
from app.rag.models import RetrievedChunk


def test_openai_adapter_preserves_embedding_input_order() -> None:
    client = Mock()
    client.embeddings.create.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(index=1, embedding=[2.0]),
            SimpleNamespace(index=0, embedding=[1.0]),
        ]
    )
    adapter = AzureOpenAIAdapter(
        client,
        embedding_deployment="embedding",
        chat_deployment="chat",
    )

    vectors = adapter.embed(["first", "second"])

    assert vectors == [[1.0], [2.0]]
    client.embeddings.create.assert_called_once_with(
        model="embedding",
        input=["first", "second"],
    )


def test_search_adapter_uploads_provenance_and_vectors() -> None:
    client = Mock()
    client.upload_documents.return_value = [SimpleNamespace(key="chunk-1", succeeded=True)]
    adapter = AzureSearchAdapter(client)
    chunk = RetrievedChunk("chunk-1", "content", "title", "source.pdf", 3)

    adapter.index([chunk], [[0.1, 0.2]])

    client.upload_documents.assert_called_once_with(
        documents=[
            {
                "id": "chunk-1",
                "content": "content",
                "title": "title",
                "source_path": "source.pdf",
                "page_number": 3,
                "section": None,
                "content_vector": [0.1, 0.2],
            }
        ]
    )


def test_search_adapter_reports_partial_index_failure() -> None:
    client = Mock()
    client.upload_documents.return_value = [SimpleNamespace(key="chunk-1", succeeded=False)]
    adapter = AzureSearchAdapter(client)
    chunk = RetrievedChunk("chunk-1", "content", "title", "source.pdf")

    with pytest.raises(RuntimeError, match="chunk-1"):
        adapter.index([chunk], [[0.1]])


def test_search_adapter_maps_hybrid_results(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client.search.return_value = [
        {
            "id": "chunk-1",
            "content": "content",
            "title": "title",
            "source_path": "source.pdf",
            "page_number": 3,
            "@search.score": 0.75,
        }
    ]
    vector_query = Mock()
    monkeypatch.setattr("app.rag.azure.VectorizedQuery", vector_query)
    adapter = AzureSearchAdapter(client)

    chunks = adapter.search("pricing", [0.1, 0.2], top=5)

    assert chunks == [RetrievedChunk("chunk-1", "content", "title", "source.pdf", 3, None, 0.75)]
    vector_query.assert_called_once_with(
        vector=[0.1, 0.2],
        k_nearest_neighbors=5,
        fields="content_vector",
    )
    search_kwargs: dict[str, Any] = client.search.call_args.kwargs
    assert search_kwargs["search_text"] == "pricing"
    assert search_kwargs["top"] == 5
