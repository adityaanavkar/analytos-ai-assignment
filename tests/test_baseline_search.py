"""Mocked contract tests for the vector-only baseline search adapter."""

from unittest.mock import Mock

import pytest

from app.baseline.search import AzureBaselineSearch
from app.config import Settings
from app.rag.models import RetrievedChunk


def test_from_settings_uses_the_baseline_index(monkeypatch: pytest.MonkeyPatch) -> None:
    search_client = Mock()
    monkeypatch.setattr("app.baseline.search.SearchClient", search_client)
    credential = Mock()
    settings = Settings(
        azure_search_endpoint="https://example.search.windows.net",
        azure_search_baseline_index="frozen-baseline-v1",
    )

    AzureBaselineSearch.from_settings(settings, credential)

    search_client.assert_called_once_with(
        endpoint="https://example.search.windows.net",
        index_name="frozen-baseline-v1",
        credential=credential,
    )


def test_search_is_vector_only_and_fixed_top_five(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client.search.return_value = [
        {
            "id": "chunk-1",
            "content": "content",
            "title": "title",
            "source_path": "Finance/policy.pdf",
            "page_number": 2,
            "section": None,
            "@search.score": 0.8,
        }
    ]
    vector_query = Mock()
    monkeypatch.setattr("app.baseline.search.VectorizedQuery", vector_query)
    adapter = AzureBaselineSearch(client)

    chunks = adapter.search([0.1, 0.2])

    assert chunks == [
        RetrievedChunk("chunk-1", "content", "title", "Finance/policy.pdf", 2, None, 0.8)
    ]
    vector_query.assert_called_once_with(
        vector=[0.1, 0.2],
        k_nearest_neighbors=5,
        fields="content_vector",
    )
    assert client.search.call_args.kwargs == {
        "search_text": None,
        "vector_queries": [vector_query.return_value],
        "select": ["id", "content", "title", "source_path", "page_number", "section"],
        "top": 5,
    }
