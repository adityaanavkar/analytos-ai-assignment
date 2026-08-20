"""Prepare or upload every supported document in the assignment knowledge base."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient

from app.config import Settings, get_settings
from app.rag.azure import AzureOpenAIAdapter, AzureSearchAdapter
from app.rag.models import RetrievedChunk
from ingestion.docx import ingest_docx
from ingestion.pdf import ingest_pdf
from ingestion.xlsx import ingest_xlsx
from scripts.mvp_ingest import VECTOR_DIMENSIONS, build_index_schema

DEFAULT_ROOT = Path("KnowledgeBase")
SUPPORTED_SUFFIXES = frozenset({".pdf", ".docx", ".xlsx"})
EMBEDDING_BATCH_SIZE = 64


@dataclass(frozen=True, slots=True)
class PreparedDocument:
    """One source document and its normalized searchable chunks."""

    path: Path
    chunks: tuple[RetrievedChunk, ...]


def discover_documents(root: Path) -> list[Path]:
    """Return every supported knowledge file in deterministic path order."""

    if not root.is_dir():
        raise FileNotFoundError(f"Knowledge-base directory does not exist: {root}")
    return sorted(
        (path for path in root.rglob("*") if path.suffix.lower() in SUPPORTED_SUFFIXES),
        key=lambda path: path.as_posix().casefold(),
    )


def prepare_document(path: Path) -> PreparedDocument:
    """Convert a supported source file into the shared Azure Search chunk model."""

    suffix = path.suffix.lower()
    title = path.stem
    if suffix == ".pdf":
        chunks = tuple(
            RetrievedChunk(
                id=chunk.chunk_id,
                content=chunk.text,
                title=title,
                source_path=chunk.source_path,
                page_number=chunk.page_number,
            )
            for chunk in ingest_pdf(path)
        )
    elif suffix == ".docx":
        chunks = tuple(
            RetrievedChunk(
                id=chunk.chunk_id,
                content=chunk.text,
                title=title,
                source_path=chunk.source_path,
                section=chunk.section,
            )
            for chunk in ingest_docx(path)
        )
    elif suffix == ".xlsx":
        chunks = tuple(
            RetrievedChunk(
                id=chunk.chunk_id,
                content=chunk.text,
                title=title,
                source_path=chunk.source_path,
                section=f"{chunk.sheet_name} row {chunk.row_number}",
            )
            for chunk in ingest_xlsx(path)
        )
    else:
        raise ValueError(f"Unsupported document type: {path.suffix}")

    if not chunks:
        raise ValueError(f"Document produced no searchable chunks: {path}")
    return PreparedDocument(path=path, chunks=chunks)


def prepare_corpus(root: Path = DEFAULT_ROOT) -> list[PreparedDocument]:
    """Prepare every supported document and reject an empty corpus."""

    documents = [prepare_document(path) for path in discover_documents(root)]
    if not documents:
        raise ValueError(f"No supported documents found under: {root}")
    return documents


def _embed_in_batches(
    chunks: Sequence[RetrievedChunk],
    openai: AzureOpenAIAdapter,
) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        batch = chunks[start : start + EMBEDDING_BATCH_SIZE]
        batch_vectors = openai.embed([chunk.content for chunk in batch])
        if len(batch_vectors) != len(batch):
            raise ValueError("Azure OpenAI returned an unexpected embedding count")
        if any(len(vector) != VECTOR_DIMENSIONS for vector in batch_vectors):
            raise ValueError(f"Every embedding must contain {VECTOR_DIMENSIONS} dimensions")
        vectors.extend(batch_vectors)
    return vectors


def upload_corpus(
    documents: Sequence[PreparedDocument],
    settings: Settings,
    credential: TokenCredential,
) -> tuple[int, int]:
    """Upsert the complete corpus and remove stale chunks from the dedicated index."""

    if not settings.azure_search_endpoint:
        raise ValueError("AZURE_SEARCH_ENDPOINT is required for upload")
    chunks = [chunk for document in documents for chunk in document.chunks]
    desired_ids = {chunk.id for chunk in chunks}
    if len(desired_ids) != len(chunks):
        raise ValueError("Chunk IDs must be unique across the complete corpus")

    index_client = SearchIndexClient(settings.azure_search_endpoint, credential)
    document_client = SearchClient(
        settings.azure_search_endpoint,
        settings.azure_search_improved_index,
        credential,
    )
    openai = AzureOpenAIAdapter.from_settings(settings, credential)
    search = AzureSearchAdapter.from_settings(settings, credential)
    try:
        index_client.create_or_update_index(
            build_index_schema(settings.azure_search_improved_index)
        )
        vectors = _embed_in_batches(chunks, openai)
        search.index(chunks, vectors)

        existing_ids = {
            str(result["id"])
            for result in document_client.search(search_text="*", select=["id"], top=1000)
        }
        stale_ids = sorted(existing_ids - desired_ids)
        if stale_ids:
            results = document_client.delete_documents(
                documents=[{"id": chunk_id} for chunk_id in stale_ids]
            )
            failed = [str(result.key) for result in results if not result.succeeded]
            if failed:
                raise RuntimeError(f"Failed to remove stale Search chunks: {', '.join(failed)}")
        return len(chunks), len(stale_ids)
    finally:
        search.close()
        openai.close()
        document_client.close()
        index_client.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare or upload all knowledge-base documents.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload the complete corpus to Azure. The default is a local dry run.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the complete-corpus ingestion command."""

    args = _build_parser().parse_args(argv)
    documents = prepare_corpus(args.root)
    chunk_count = sum(len(document.chunks) for document in documents)
    print(f"Mode: {'upload' if args.upload else 'dry-run'}")
    print(f"Documents: {len(documents)}")
    print(f"Chunks: {chunk_count}")
    for document in documents:
        print(f"- {document.path.as_posix()}: {len(document.chunks)} chunks")

    if not args.upload:
        print("No Azure calls were made. Add --upload to reconcile the dedicated Search index.")
        return 0

    settings = get_settings()
    credential = DefaultAzureCredential()
    try:
        uploaded, removed = upload_corpus(documents, settings, credential)
    finally:
        credential.close()
    print(f"Uploaded chunks: {uploaded}")
    print(f"Removed stale chunks: {removed}")
    print(f"Azure Search index: {settings.azure_search_improved_index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
