"""Tests for complete-corpus preparation and safe incremental reconciliation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.documents.metadata import load_document_manifest
from app.rag.models import RetrievedChunk, sha256_text
from app.rag.retrieval_policy import select_retrieval_context
from app.rag.search_documents import chunk_to_search_document
from ingestion.sources import AzureBlobSource
from scripts.ingest_all import (
    discover_documents,
    prepare_corpus,
    prepare_document,
    reconcile_chunks,
)
from scripts.mvp_ingest import VECTOR_DIMENSIONS


@dataclass(frozen=True)
class _Blob:
    name: str
    size: int
    etag: str = '"etag"'


class _Download:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def readall(self) -> bytes:
        return self._payload


class _Container:
    def __init__(self, name: str, payload: bytes) -> None:
        self._name = name
        self._payload = payload

    def list_blobs(self) -> list[_Blob]:
        return [_Blob(self._name, len(self._payload))]

    def download_blob(self, blob: str) -> _Download:
        assert blob == self._name
        return _Download(self._payload)


class _TransientError(RuntimeError):
    status_code = 429


def _chunk(chunk_id: str, content: str = "content") -> RetrievedChunk:
    return RetrievedChunk(
        id=chunk_id,
        content=content,
        title="Title",
        source_path="KnowledgeBase/Finance/Document.pdf",
        content_hash=sha256_text(content),
        document_id="document-id",
        file_type="pdf",
        department="Finance",
        document_type="policy",
        version="1.0",
        is_current=True,
        allowed_groups=("employees",),
    )


def _search_document(chunk: RetrievedChunk) -> dict[str, object]:
    document = chunk_to_search_document(chunk, [0.0])
    del document["content_vector"]
    return document


def test_discovery_finds_every_assignment_document() -> None:
    documents = discover_documents(Path("KnowledgeBase"))

    assert len(documents) == 11
    assert {path.suffix.lower() for path in documents} == {".pdf", ".docx", ".xlsx"}


def test_prepare_corpus_preserves_every_source_and_unique_chunk_id() -> None:
    documents = prepare_corpus()
    chunks = [chunk for document in documents for chunk in document.chunks]

    assert len(documents) == 11
    assert len(chunks) == 190
    assert len({chunk.id for chunk in chunks}) == len(chunks)
    assert {chunk.source_path for chunk in chunks} == {
        document.metadata.source_path for document in documents
    }
    assert all(chunk.document_id for chunk in chunks)
    assert all(chunk.content_hash == sha256_text(chunk.content) for chunk in chunks)
    assert all(chunk.file_type in {"pdf", "docx", "xlsx"} for chunk in chunks)
    assert all(chunk.department in {"Finance", "HR", "IT", "Legal", "Sales"} for chunk in chunks)
    assert all(chunk.document_type for chunk in chunks)
    assert all(chunk.version for chunk in chunks)
    assert all(chunk.is_current is not None for chunk in chunks)
    assert all(chunk.allowed_groups for chunk in chunks)


def test_complete_corpus_preserves_format_specific_provenance() -> None:
    documents = prepare_corpus()
    chunks = [chunk for document in documents for chunk in document.chunks]

    assert any(chunk.file_type == "pdf" and chunk.page_number == 2 for chunk in chunks)
    assert any(
        chunk.file_type == "docx"
        and chunk.section
        and chunk.table_number is not None
        and chunk.row_number is not None
        for chunk in chunks
    )
    assert any(
        chunk.file_type == "xlsx"
        and chunk.sheet_name == "Approval Thresholds"
        and chunk.section == "Approval Thresholds grouped rows 1-11"
        and "Chief Revenue Officer + Finance Business Partner" in chunk.content
        for chunk in chunks
    )
    assert any(
        chunk.file_type == "xlsx"
        and chunk.sheet_name == "Volume Discounts"
        and chunk.table_number == 1
        and chunk.row_number is not None
        for chunk in chunks
    )


def test_canonical_ids_are_stable_across_repeated_preparation() -> None:
    path = Path("KnowledgeBase/Sales/Discounts.xlsx")

    first = prepare_document(path)
    second = prepare_document(path.resolve())

    assert [chunk.id for chunk in first.chunks] == [chunk.id for chunk in second.chunks]
    assert {chunk.document_id for chunk in first.chunks} == {first.chunks[0].document_id}


def test_group_chunks_recover_core_004_from_an_initial_wrong_approval_row() -> None:
    chunks = list(prepare_document(Path("KnowledgeBase/Sales/Discounts.xlsx")).chunks)
    groups = [chunk for chunk in chunks if chunk.section and "grouped rows" in chunk.section]
    rows = [chunk for chunk in chunks if chunk not in groups]
    wrong_approval = next(
        chunk
        for chunk in rows
        if chunk.sheet_name == "Approval Thresholds" and chunk.row_number == 6
    )
    candidates = (wrong_approval, *rows[:15], *groups)[:20]

    selected = select_retrieval_context(
        (
            "For 250 OrbitSuite seats on an annual prepaid term, what combined discount "
            "and final monthly per-seat price apply, and who approves the deal?"
        ),
        candidates,
    )

    evidence = "\n".join(chunk.content for chunk in selected)
    assert "Seat Count Tier=250–499 seats" in evidence
    assert "Billing Term=Annual (prepaid); Discount %=0.15" in evidence
    assert "Combined Discount Range=30% – 40%" in evidence
    assert "Chief Revenue Officer + Finance Business Partner" in evidence


def test_prepare_document_rejects_an_unsupported_type(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("not supported", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported document type"):
        prepare_document(path)


def test_local_and_blob_inputs_produce_identical_canonical_chunks() -> None:
    local_path = Path("KnowledgeBase/Finance/ExpensePolicy.pdf")
    payload = local_path.read_bytes()
    metadata = load_document_manifest()[local_path.as_posix().casefold()]
    local = prepare_document(local_path, metadata)

    with AzureBlobSource(
        _Container(local_path.as_posix(), payload)
    ).materialize() as materialization:
        blob = prepare_document(materialization.sources[0].local_path, metadata)

    assert blob.chunks == local.chunks


def test_transient_embedding_failure_retries_then_succeeds() -> None:
    chunk = _chunk("chunk-1")
    document_client = Mock()
    document_client.search.return_value = []
    embedder = Mock()
    embedder.embed.side_effect = [
        _TransientError("rate limited"),
        [[0.1] * VECTOR_DIMENSIONS],
    ]
    indexer = Mock()

    report = reconcile_chunks(
        [chunk],
        document_client=document_client,
        embedder=embedder,
        indexer=indexer,
        sleep=lambda _: None,
    )

    assert report.succeeded
    assert report.uploaded == 1
    assert report.retries == 1
    assert embedder.embed.call_count == 2
    indexer.index.assert_called_once()


def test_permanent_batch_failure_is_reported_and_prevents_stale_deletion() -> None:
    good = _chunk("good", "good content")
    bad = _chunk("bad", "bad content")
    stale = _chunk("stale", "old content")
    document_client = Mock()
    document_client.search.return_value = [_search_document(stale)]
    indexer = Mock()

    class SelectiveEmbedder:
        def embed(self, texts: Sequence[str]) -> list[list[float]]:
            if texts == ["bad content"]:
                raise ValueError("permanent invalid input")
            return [[0.1] * VECTOR_DIMENSIONS for _ in texts]

    report = reconcile_chunks(
        [good, bad],
        document_client=document_client,
        embedder=SelectiveEmbedder(),
        indexer=indexer,
        batch_size=1,
        max_workers=2,
        sleep=lambda _: None,
    )

    assert not report.succeeded
    assert report.uploaded == 1
    assert report.deleted == 0
    assert len(report.failures) == 1
    assert report.failures[0].items == ("bad",)
    document_client.delete_documents.assert_not_called()


def test_identical_second_run_is_a_true_embedding_and_upload_no_op() -> None:
    chunks = [_chunk("one", "first"), _chunk("two", "second")]
    document_client = Mock()
    document_client.search.return_value = [_search_document(chunk) for chunk in chunks]
    embedder = Mock()
    indexer = Mock()

    report = reconcile_chunks(
        chunks,
        document_client=document_client,
        embedder=embedder,
        indexer=indexer,
        sleep=lambda _: None,
    )

    assert report.succeeded
    assert report.unchanged == 2
    assert report.uploaded == 0
    assert report.deleted == 0
    embedder.embed.assert_not_called()
    indexer.index.assert_not_called()
    document_client.delete_documents.assert_not_called()


def test_stale_chunks_are_deleted_only_after_every_batch_succeeds() -> None:
    desired = _chunk("desired")
    stale = _chunk("stale", "old")
    document_client = Mock()
    document_client.search.return_value = [_search_document(stale)]
    document_client.delete_documents.return_value = [SimpleNamespace(key="stale", succeeded=True)]
    embedder = Mock()
    embedder.embed.return_value = [[0.1] * VECTOR_DIMENSIONS]
    indexer = Mock()

    report = reconcile_chunks(
        [desired],
        document_client=document_client,
        embedder=embedder,
        indexer=indexer,
        sleep=lambda _: None,
    )

    assert report.succeeded
    assert report.deleted == 1
    document_client.delete_documents.assert_called_once_with(documents=[{"id": "stale"}])
