"""Mocked tests for the first document-to-Azure ingestion CLI."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from app.config import Settings
from app.rag.azure import AzureOpenAIAdapter, AzureSearchAdapter
from scripts import mvp_ingest

EXPENSE_POLICY = Path("KnowledgeBase/Finance/ExpensePolicy.pdf")


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        azure_openai_endpoint="https://openai.example.test",
        azure_openai_chat_deployment="chat",
        azure_openai_embedding_deployment="embedding",
        azure_search_endpoint="https://search.example.test",
        azure_storage_account_url="https://storage.example.test",
    )


def test_dry_run_uses_real_document_without_azure_calls(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    credential = Mock(side_effect=AssertionError("dry-run must not create a credential"))
    monkeypatch.setattr(mvp_ingest, "DefaultAzureCredential", credential)

    result = mvp_ingest.main(
        [
            "--document",
            str(EXPENSE_POLICY),
            "--chunk-size-words",
            "80",
            "--overlap-words",
            "20",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "Mode: dry-run" in output
    assert "Extracted pages: 2" in output
    assert "Prepared chunks:" in output
    assert "No Azure calls were made" in output
    credential.assert_not_called()


def test_index_schema_has_1536_dimension_hnsw_profile() -> None:
    schema = mvp_ingest.build_index_schema("test-index")

    fields = {field.name: field for field in schema.fields}
    vector_field = fields["content_vector"]
    assert fields["id"].key is True
    assert vector_field.vector_search_dimensions == 1536
    assert vector_field.vector_search_profile_name == "mvp-vector-profile"
    assert schema.vector_search is not None
    algorithms = schema.vector_search.algorithms
    profiles = schema.vector_search.profiles
    assert algorithms is not None
    assert profiles is not None
    assert algorithms[0].name == "mvp-hnsw"
    assert profiles[0].algorithm_configuration_name == "mvp-hnsw"


def test_upload_creates_index_embeds_and_uploads(monkeypatch: pytest.MonkeyPatch) -> None:
    _, chunks = mvp_ingest.load_document_chunks(
        EXPENSE_POLICY,
        chunk_size_words=2000,
        overlap_words=0,
    )
    credential = Mock()
    index_client = Mock()
    index_client_type = Mock(return_value=index_client)
    openai = Mock()
    openai.embed.return_value = [[0.0] * 1536 for _ in chunks]
    search = Mock()
    monkeypatch.setattr(mvp_ingest, "SearchIndexClient", index_client_type)
    monkeypatch.setattr(
        AzureOpenAIAdapter,
        "from_settings",
        Mock(return_value=openai),
    )
    monkeypatch.setattr(
        AzureSearchAdapter,
        "from_settings",
        Mock(return_value=search),
    )

    settings = _settings()
    mvp_ingest.upload_chunks(chunks, settings, credential)

    index_client_type.assert_called_once_with(
        endpoint="https://search.example.test",
        credential=credential,
    )
    created_schema = index_client.create_or_update_index.call_args.args[0]
    assert created_schema.name == settings.azure_search_improved_index
    openai.embed.assert_called_once_with([chunk.content for chunk in chunks])
    search.index.assert_called_once_with(chunks, openai.embed.return_value)
    search.close.assert_called_once_with()
    openai.close.assert_called_once_with()
    index_client.close.assert_called_once_with()


def test_upload_rejects_wrong_embedding_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    _, chunks = mvp_ingest.load_document_chunks(
        EXPENSE_POLICY,
        chunk_size_words=2000,
        overlap_words=0,
    )
    index_client = Mock()
    openai = Mock()
    openai.embed.return_value = [[0.0] for _ in chunks]
    search = Mock()
    monkeypatch.setattr(
        mvp_ingest,
        "SearchIndexClient",
        Mock(return_value=index_client),
    )
    monkeypatch.setattr(
        AzureOpenAIAdapter,
        "from_settings",
        Mock(return_value=openai),
    )
    monkeypatch.setattr(
        AzureSearchAdapter,
        "from_settings",
        Mock(return_value=search),
    )

    with pytest.raises(ValueError, match="1536-dimension"):
        mvp_ingest.upload_chunks(chunks, _settings(), Mock())

    search.index.assert_not_called()
