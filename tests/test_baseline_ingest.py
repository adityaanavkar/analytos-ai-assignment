"""Tests for deterministic complete-corpus baseline ingestion."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.config import Settings
from app.rag.azure import AzureOpenAIAdapter
from app.rag.models import RetrievedChunk
from scripts import baseline_ingest


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        azure_openai_endpoint="https://openai.example.test",
        azure_openai_chat_deployment="chat",
        azure_openai_embedding_deployment="embedding",
        azure_search_endpoint="https://search.example.test",
        azure_storage_account_url="https://storage.example.test",
    )


def test_dry_run_discovers_all_documents_without_azure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    credential = Mock(side_effect=AssertionError("dry-run must not create credentials"))
    monkeypatch.setattr(baseline_ingest, "DefaultAzureCredential", credential)

    result = baseline_ingest.main([])

    output = capsys.readouterr().out
    assert result == 0
    assert "Mode: dry-run" in output
    assert "Documents: 11" in output
    assert "Chunks: 53" in output
    assert "120 words with 20-word overlap" in output
    assert "Embedding dimensions: 1536" in output
    assert "AZURE_SEARCH_BASELINE_INDEX" in output
    fingerprint_line = next(line for line in output.splitlines() if "Corpus fingerprint:" in line)
    assert len(fingerprint_line.removeprefix("Corpus fingerprint: ")) == 64
    assert "No Azure calls were made" in output
    credential.assert_not_called()


def test_complete_corpus_has_stable_scoped_ids_and_exact_overlap() -> None:
    first = baseline_ingest.prepare_corpus()
    second = baseline_ingest.prepare_corpus()
    first_chunks = [chunk for document in first for chunk in document.chunks]
    second_chunks = [chunk for document in second for chunk in document.chunks]

    assert len(first) == 11
    assert len(first_chunks) == 53
    assert len({chunk.source_path for chunk in first_chunks}) == 11
    assert all(chunk.id.startswith("baseline-") for chunk in first_chunks)
    assert len({chunk.id for chunk in first_chunks}) == len(first_chunks)
    assert [chunk.id for chunk in first_chunks] == [chunk.id for chunk in second_chunks]
    assert baseline_ingest.corpus_fingerprint(first) == baseline_ingest.corpus_fingerprint(second)

    for document in first:
        for left, right in zip(document.chunks, document.chunks[1:], strict=False):
            assert len(left.content.split()) == 120
            assert left.content.split()[-20:] == right.content.split()[:20]
        assert 0 < len(document.chunks[-1].content.split()) <= 120


def test_flattening_drops_structural_provenance_from_baseline_chunks() -> None:
    documents = baseline_ingest.prepare_corpus()
    chunks = [chunk for document in documents for chunk in document.chunks]

    assert all(chunk.page_number is None for chunk in chunks)
    assert all(chunk.section is None for chunk in chunks)
    assert all("Workbook:" not in chunk.content for chunk in chunks)
    assert all("Table headers:" not in chunk.content for chunk in chunks)


def test_baseline_schema_is_vector_only_without_semantic_configuration() -> None:
    schema = baseline_ingest.build_baseline_index_schema("baseline-test")
    fields = {field.name: field for field in schema.fields}

    assert fields["content_vector"].vector_search_dimensions == 1536
    assert fields["content_vector"].vector_search_profile_name == "baseline-vector-profile"
    assert schema.semantic_search is None
    assert schema.vector_search is not None
    assert schema.vector_search.algorithms is not None
    assert schema.vector_search.profiles is not None
    assert schema.vector_search.algorithms[0].name == "baseline-hnsw"


def test_embedding_is_batched_at_64_and_validated() -> None:
    chunks = [
        RetrievedChunk(f"baseline-{index}", f"content {index}", "title", "source.pdf")
        for index in range(130)
    ]
    openai = Mock(spec=AzureOpenAIAdapter)
    openai.embed.side_effect = lambda texts: [[0.0] * 1536 for _ in texts]

    vectors = baseline_ingest.embed_in_batches(chunks, openai)

    assert len(vectors) == 130
    assert [len(call.args[0]) for call in openai.embed.call_args_list] == [64, 64, 2]


def test_upload_uses_baseline_index_and_reconciles_stale_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = baseline_ingest.BaselineDocument(
        path=Path("KnowledgeBase/example.pdf"),
        chunks=(RetrievedChunk("baseline-current", "text", "example", "source.pdf"),),
    )
    index_client = Mock()
    document_client = Mock()
    document_client.search.return_value = [
        {"id": "baseline-current"},
        {"id": "baseline-stale"},
    ]
    document_client.delete_documents.return_value = [
        SimpleNamespace(key="baseline-stale", succeeded=True)
    ]
    search = Mock()
    openai = Mock()
    openai.embed.return_value = [[0.0] * 1536]
    monkeypatch.setattr(baseline_ingest, "SearchIndexClient", Mock(return_value=index_client))
    search_client_type = Mock(return_value=document_client)
    monkeypatch.setattr(baseline_ingest, "SearchClient", search_client_type)
    monkeypatch.setattr(baseline_ingest, "AzureSearchAdapter", Mock(return_value=search))
    monkeypatch.setattr(
        AzureOpenAIAdapter,
        "from_settings",
        Mock(return_value=openai),
    )

    settings = _settings()
    uploaded, removed = baseline_ingest.upload_corpus([document], settings, Mock())

    assert (uploaded, removed) == (1, 1)
    assert search_client_type.call_args.args[1] == settings.azure_search_baseline_index
    schema = index_client.create_or_update_index.call_args.args[0]
    assert schema.name == settings.azure_search_baseline_index
    search.index.assert_called_once_with(list(document.chunks), openai.embed.return_value)
    document_client.delete_documents.assert_called_once_with(documents=[{"id": "baseline-stale"}])


def test_missing_root_and_unsupported_file_fail_clearly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Knowledge-base directory"):
        baseline_ingest.discover_documents(tmp_path / "missing")
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("text", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported document type"):
        baseline_ingest.flatten_document(unsupported)
