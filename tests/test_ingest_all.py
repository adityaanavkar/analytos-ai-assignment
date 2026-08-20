"""Tests for complete-corpus preparation and reconciliation helpers."""

from pathlib import Path

import pytest

from scripts.ingest_all import discover_documents, prepare_corpus, prepare_document


def test_discovery_finds_every_assignment_document() -> None:
    documents = discover_documents(Path("KnowledgeBase"))

    assert len(documents) == 11
    assert {path.suffix.lower() for path in documents} == {".pdf", ".docx", ".xlsx"}


def test_prepare_corpus_preserves_every_source_and_unique_chunk_id() -> None:
    documents = prepare_corpus()
    chunks = [chunk for document in documents for chunk in document.chunks]

    assert len(documents) == 11
    assert len(chunks) == 186
    assert len({chunk.id for chunk in chunks}) == len(chunks)
    assert {chunk.source_path for chunk in chunks} == {
        document.path.as_posix() for document in documents
    }


def test_prepare_document_rejects_an_unsupported_type(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("not supported", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported document type"):
        prepare_document(path)
