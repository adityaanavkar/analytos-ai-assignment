"""Mocked tests for direct Azure SDK adapters."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from azure.core.exceptions import HttpResponseError

from app.rag.azure import (
    SEMANTIC_CONFIGURATION_NAME,
    AzureOpenAIAdapter,
    AzureSearchAdapter,
)
from app.rag.models import IndexedDocument, RetrievedChunk
from app.rag.search_documents import SEARCH_CHUNK_FIELDS


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


def test_openai_adapter_exposes_deployments_and_exact_generation_text() -> None:
    client = Mock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Answer [chunk-1]."))]
    )
    adapter = AzureOpenAIAdapter(
        client,
        embedding_deployment="embedding-deployment",
        chat_deployment="chat-deployment",
    )
    chunk = RetrievedChunk("chunk-1", "Evidence text", "Policy", "Policy.pdf")

    answer = adapter.generate("What is documented?", [chunk])
    generation_inputs = adapter.generation_input_texts("What is documented?", [chunk])

    assert answer == "Answer [chunk-1]."
    assert adapter.embedding_deployment == "embedding-deployment"
    assert adapter.chat_deployment == "chat-deployment"
    assert "using only the supplied evidence" in generation_inputs[0]
    assert generation_inputs[1] == (
        "Question: What is documented?\n\nEvidence:\n[chunk-1] Policy\nEvidence text"
    )
    messages = client.chat.completions.create.call_args.kwargs["messages"]
    assert [message["content"] for message in messages] == list(generation_inputs)


def test_generation_prompt_requires_concise_grounded_claims_and_safe_citations() -> None:
    system_input, _ = AzureOpenAIAdapter.generation_input_texts(
        "What is the policy limit?",
        [RetrievedChunk("chunk-1", "Evidence text", "Policy", "Policy.pdf")],
    )

    assert "directly and concisely" in system_input
    assert "Ignore evidence that is irrelevant" in system_input
    assert "Do not invent, extrapolate, or fill gaps" in system_input
    assert "Do not calculate or combine values unless" in system_input
    assert "exact supporting chunk ID" in system_input
    assert "never invent citation IDs" in system_input
    assert "do not guess" in system_input


def test_generation_prompt_handles_missing_evidence_without_inviting_a_guess() -> None:
    system_input, user_input = AzureOpenAIAdapter.generation_input_texts("Unknown?", [])

    assert "not enough supporting information in the knowledge base" in system_input
    assert user_input == "Question: Unknown?\n\nEvidence:\n"


def test_search_adapter_uploads_provenance_and_vectors() -> None:
    client = Mock()
    client.upload_documents.return_value = [SimpleNamespace(key="chunk-1", succeeded=True)]
    adapter = AzureSearchAdapter(client)
    chunk = RetrievedChunk("chunk-1", "content", "title", "source.pdf", 3)

    adapter.index([chunk], [[0.1, 0.2]])

    documents = client.upload_documents.call_args.kwargs["documents"]
    assert len(documents) == 1
    assert documents[0]["id"] == "chunk-1"
    assert documents[0]["page_number"] == 3
    assert documents[0]["content_vector"] == [0.1, 0.2]
    assert set(documents[0]) == {*SEARCH_CHUNK_FIELDS, "content_vector"}


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
    assert search_kwargs["select"] == list(SEARCH_CHUNK_FIELDS)
    assert search_kwargs["query_type"] == "semantic"
    assert search_kwargs["semantic_configuration_name"] == SEMANTIC_CONFIGURATION_NAME


def test_search_adapter_falls_back_to_hybrid_when_semantic_is_unavailable() -> None:
    client = Mock()
    unavailable = HttpResponseError(message="semantic unavailable")
    unavailable.status_code = 400
    hybrid_result = {
        "id": "chunk-1",
        "content": "content",
        "title": "title",
        "source_path": "source.pdf",
    }
    client.search.side_effect = [unavailable, [hybrid_result]]
    adapter = AzureSearchAdapter(client)

    chunks = adapter.search("pricing", [0.1], top=20)

    assert [chunk.id for chunk in chunks] == ["chunk-1"]
    semantic_kwargs = client.search.call_args_list[0].kwargs
    fallback_kwargs = client.search.call_args_list[1].kwargs
    assert semantic_kwargs["query_type"] == "semantic"
    assert "query_type" not in fallback_kwargs
    assert fallback_kwargs["search_text"] == "pricing"
    assert fallback_kwargs["top"] == 20


def test_search_adapter_does_not_hide_non_capability_semantic_failures() -> None:
    client = Mock()
    service_failure = HttpResponseError(message="service unavailable")
    service_failure.status_code = 503
    client.search.side_effect = service_failure
    adapter = AzureSearchAdapter(client)

    with pytest.raises(HttpResponseError, match="service unavailable"):
        adapter.search("pricing", [0.1], top=20)

    assert client.search.call_count == 1


def test_search_adapter_can_disable_semantic_query_explicitly() -> None:
    client = Mock()
    client.search.return_value = []
    adapter = AzureSearchAdapter(client, semantic_enabled=False)

    assert adapter.search("pricing", [0.1], top=20) == []

    kwargs = client.search.call_args.kwargs
    assert "query_type" not in kwargs
    assert "semantic_configuration_name" not in kwargs


def test_search_inventory_deduplicates_chunks_and_normalizes_paths() -> None:
    client = Mock()
    client.search.return_value = [
        {"title": "Travel Policy", "source_path": "Finance\\TravelPolicy.docx"},
        {"title": "Travel Policy", "source_path": "Finance/TravelPolicy.docx"},
        {"title": "Benefits", "source_path": "HR/Benefits.pdf"},
    ]
    adapter = AzureSearchAdapter(client)

    documents = adapter.inventory()

    assert documents == [
        IndexedDocument("Travel Policy", "Finance/TravelPolicy.docx"),
        IndexedDocument("Benefits", "HR/Benefits.pdf"),
    ]
    client.search.assert_called_once_with(
        search_text="*",
        select=["title", "source_path"],
        top=1000,
    )
