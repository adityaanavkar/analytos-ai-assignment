"""Dry-run or upload the first real document through the Azure RAG adapters."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

from app.config import Settings, get_settings
from app.rag.azure import (
    SEMANTIC_CONFIGURATION_NAME,
    AzureOpenAIAdapter,
    AzureSearchAdapter,
)
from app.rag.models import RetrievedChunk
from ingestion.pdf import chunk_pages, extract_pdf

DEFAULT_DOCUMENT = Path("KnowledgeBase/Finance/ExpensePolicy.pdf")
VECTOR_DIMENSIONS = 1536
_ALGORITHM_NAME = "mvp-hnsw"
_PROFILE_NAME = "mvp-vector-profile"


def build_index_schema(index_name: str) -> SearchIndex:
    """Return the minimal index schema shared by upload and hybrid retrieval."""

    return SearchIndex(
        name=index_name,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SimpleField(
                name="content_hash",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SimpleField(
                name="document_id",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SearchableField(name="title", type=SearchFieldDataType.String),
            SimpleField(
                name="source_path",
                type=SearchFieldDataType.String,
                filterable=True,
            ),
            SimpleField(name="file_type", type=SearchFieldDataType.String, filterable=True),
            SimpleField(
                name="department",
                type=SearchFieldDataType.String,
                filterable=True,
                facetable=True,
            ),
            SimpleField(
                name="document_type",
                type=SearchFieldDataType.String,
                filterable=True,
                facetable=True,
            ),
            SimpleField(name="version", type=SearchFieldDataType.String, filterable=True),
            SimpleField(
                name="effective_from",
                type=SearchFieldDataType.DateTimeOffset,
                filterable=True,
                sortable=True,
            ),
            SimpleField(
                name="effective_to",
                type=SearchFieldDataType.DateTimeOffset,
                filterable=True,
                sortable=True,
            ),
            SimpleField(
                name="is_current",
                type=SearchFieldDataType.Boolean,
                filterable=True,
            ),
            SimpleField(
                name="page_number",
                type=SearchFieldDataType.Int32,
                filterable=True,
            ),
            SimpleField(name="section", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="sheet_name", type=SearchFieldDataType.String, filterable=True),
            SimpleField(
                name="table_number",
                type=SearchFieldDataType.Int32,
                filterable=True,
            ),
            SimpleField(
                name="row_number",
                type=SearchFieldDataType.Int32,
                filterable=True,
            ),
            SearchField(
                name="allowed_groups",
                type=SearchFieldDataType.Collection(SearchFieldDataType.String),
                searchable=False,
                filterable=True,
            ),
            SearchField(
                name="content_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=VECTOR_DIMENSIONS,
                vector_search_profile_name=_PROFILE_NAME,
            ),
        ],
        vector_search=VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name=_ALGORITHM_NAME)],
            profiles=[
                VectorSearchProfile(
                    name=_PROFILE_NAME,
                    algorithm_configuration_name=_ALGORITHM_NAME,
                )
            ],
        ),
        semantic_search=SemanticSearch(
            configurations=[
                SemanticConfiguration(
                    name=SEMANTIC_CONFIGURATION_NAME,
                    prioritized_fields=SemanticPrioritizedFields(
                        title_field=SemanticField(field_name="title"),
                        content_fields=[SemanticField(field_name="content")],
                    ),
                )
            ]
        ),
    )


def load_document_chunks(
    document: Path,
    *,
    chunk_size_words: int,
    overlap_words: int,
) -> tuple[int, list[RetrievedChunk]]:
    """Extract the PDF and adapt local chunks to the RAG search model."""

    pages = extract_pdf(document)
    local_chunks = chunk_pages(
        pages,
        chunk_size_words=chunk_size_words,
        overlap_words=overlap_words,
    )
    title = document.stem
    chunks = [
        RetrievedChunk(
            id=chunk.chunk_id,
            content=chunk.text,
            title=title,
            source_path=chunk.source_path,
            page_number=chunk.page_number,
        )
        for chunk in local_chunks
    ]
    return len(pages), chunks


def _validate_vectors(vectors: Sequence[Sequence[float]], expected_count: int) -> None:
    if len(vectors) != expected_count:
        raise ValueError(
            f"Azure OpenAI returned {len(vectors)} vectors for {expected_count} chunks"
        )
    invalid = [
        position for position, vector in enumerate(vectors) if len(vector) != VECTOR_DIMENSIONS
    ]
    if invalid:
        positions = ", ".join(str(position) for position in invalid)
        raise ValueError(
            f"Expected {VECTOR_DIMENSIONS}-dimension embeddings; "
            f"invalid chunk positions: {positions}"
        )


def upload_chunks(
    chunks: Sequence[RetrievedChunk],
    settings: Settings,
    credential: TokenCredential,
) -> None:
    """Create the index, embed the chunks, and upload them with Entra auth."""

    if settings.azure_auth_mode != "entra":
        raise ValueError("MVP ingestion supports only AZURE_AUTH_MODE=entra")
    if not settings.azure_search_endpoint:
        raise ValueError("AZURE_SEARCH_ENDPOINT is required for --upload")

    index_client = SearchIndexClient(
        endpoint=settings.azure_search_endpoint,
        credential=credential,
    )
    openai = AzureOpenAIAdapter.from_settings(settings, credential)
    search = AzureSearchAdapter.from_settings(settings, credential)
    try:
        index_client.create_or_update_index(
            build_index_schema(settings.azure_search_improved_index)
        )
        vectors = openai.embed([chunk.content for chunk in chunks])
        _validate_vectors(vectors, len(chunks))
        search.index(chunks, vectors)
    finally:
        search.close()
        openai.close()
        index_client.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare the Expense Policy chunks, with optional live Azure upload.",
    )
    parser.add_argument("--document", type=Path, default=DEFAULT_DOCUMENT)
    parser.add_argument("--chunk-size-words", type=int, default=120)
    parser.add_argument("--overlap-words", type=int, default=20)
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Create/update the Azure Search index, embed, and upload. Default is dry-run.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the beginner-safe CLI and return a process exit code."""

    args = _build_parser().parse_args(argv)
    page_count, chunks = load_document_chunks(
        args.document,
        chunk_size_words=args.chunk_size_words,
        overlap_words=args.overlap_words,
    )
    mode = "upload" if args.upload else "dry-run"
    print(f"Mode: {mode}")
    print(f"Document: {args.document.as_posix()}")
    print(f"Extracted pages: {page_count}")
    print(f"Prepared chunks: {len(chunks)}")

    if not args.upload:
        print("No Azure calls were made. Add --upload only after reviewing .env settings.")
        return 0

    if not chunks:
        raise ValueError("The document produced no searchable chunks")

    settings = get_settings()
    credential = DefaultAzureCredential()
    try:
        upload_chunks(chunks, settings, credential)
    finally:
        credential.close()
    print(f"Uploaded chunks: {len(chunks)}")
    print(f"Azure Search index: {settings.azure_search_improved_index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
