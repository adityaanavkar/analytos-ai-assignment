"""Tests for canonical Search serialization and deterministic identity."""

from dataclasses import replace
from datetime import UTC, date, datetime

from app.rag.models import (
    RetrievedChunk,
    deterministic_chunk_id,
    deterministic_document_id,
    sha256_text,
)
from app.rag.search_documents import chunk_from_search_result, chunk_to_search_document


def _canonical_chunk() -> RetrievedChunk:
    content = "Grounded policy evidence."
    content_hash = sha256_text(content)
    document_id = deterministic_document_id("KnowledgeBase/Finance/Policy.pdf")
    return RetrievedChunk(
        id=deterministic_chunk_id(document_id, "pdf:1:1", content_hash),
        content=content,
        title="Policy",
        source_path="KnowledgeBase/Finance/Policy.pdf",
        page_number=1,
        section="Limits",
        document_id=document_id,
        content_hash=content_hash,
        file_type="pdf",
        department="Finance",
        document_type="policy",
        version="2.0",
        effective_from=date(2026, 1, 1),
        is_current=True,
        allowed_groups=("employees", "finance"),
    )


def test_identity_helpers_are_deterministic_and_content_sensitive() -> None:
    document_id = deterministic_document_id("KnowledgeBase/Finance/Policy.pdf")
    content_hash = sha256_text("content")

    assert document_id == deterministic_document_id("knowledgebase/finance/policy.pdf")
    assert content_hash == sha256_text("content")
    assert content_hash != sha256_text("changed")
    assert deterministic_chunk_id(document_id, "pdf:1:1", content_hash) == (
        deterministic_chunk_id(document_id, "pdf:1:1", content_hash)
    )
    assert deterministic_chunk_id(document_id, "pdf:1:1", content_hash) != (
        deterministic_chunk_id(document_id, "pdf:1:2", content_hash)
    )


def test_search_serialization_round_trip_preserves_canonical_metadata() -> None:
    chunk = _canonical_chunk()
    document = chunk_to_search_document(chunk, [0.1, 0.2])
    document["@search.score"] = 0.9

    restored = chunk_from_search_result(document)

    assert document["effective_from"] == datetime(2026, 1, 1, tzinfo=UTC)
    assert document["allowed_groups"] == ["employees", "finance"]
    assert document["content_vector"] == [0.1, 0.2]
    assert restored == replace(chunk, score=0.9)
