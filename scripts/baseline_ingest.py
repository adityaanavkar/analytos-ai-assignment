"""Prepare or upload the deliberately simple vector-only baseline corpus."""

from __future__ import annotations

import argparse
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.config import Settings, get_settings
from app.rag.azure import AzureOpenAIAdapter, AzureSearchAdapter
from app.rag.models import RetrievedChunk
from ingestion.pdf import extract_pdf
from ingestion.xlsx import extract_xlsx

DEFAULT_ROOT = Path("KnowledgeBase")
SUPPORTED_SUFFIXES = frozenset({".pdf", ".docx", ".xlsx"})
CHUNK_SIZE_WORDS = 120
OVERLAP_WORDS = 20
EMBEDDING_BATCH_SIZE = 64
VECTOR_DIMENSIONS = 1536
_ALGORITHM_NAME = "baseline-hnsw"
_PROFILE_NAME = "baseline-vector-profile"


@dataclass(frozen=True, slots=True)
class BaselineDocument:
    """One flattened source document and its fixed-size baseline chunks."""

    path: Path
    chunks: tuple[RetrievedChunk, ...]


def discover_documents(root: Path = DEFAULT_ROOT) -> list[Path]:
    """Discover every supported source in deterministic path order."""

    if not root.is_dir():
        raise FileNotFoundError(f"Knowledge-base directory does not exist: {root}")
    return sorted(
        (path for path in root.rglob("*") if path.suffix.lower() in SUPPORTED_SUFFIXES),
        key=lambda path: path.as_posix().casefold(),
    )


def _normalise(text: str) -> str:
    return " ".join(text.split())


def _flatten_pdf(path: Path) -> str:
    return " ".join(page.text for page in extract_pdf(path))


def _flatten_docx(path: Path) -> str:
    """Read paragraphs and raw table cells in order without section grouping."""

    parts: list[str] = []
    document = Document(str(path))
    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            text = _normalise(item.text)
            if text:
                parts.append(text)
        elif isinstance(item, Table):
            for row in item.rows:
                values = [_normalise(cell.text) for cell in row.cells]
                parts.extend(value for value in values if value)
    return " ".join(parts)


def _flatten_xlsx(path: Path) -> str:
    """Read cell values in sheet and row order without table-aware rendering."""

    workbook = extract_xlsx(path)
    parts: list[str] = []
    for sheet in workbook.sheets:
        for row in sheet.rows:
            for cell in row.cells:
                value = cell.value or cell.formula
                if value:
                    parts.append(_normalise(value))
    return " ".join(parts)


def flatten_document(path: Path) -> str:
    """Return one plain word stream for a supported document."""

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _flatten_pdf(path)
    elif suffix == ".docx":
        text = _flatten_docx(path)
    elif suffix == ".xlsx":
        text = _flatten_xlsx(path)
    else:
        raise ValueError(f"Unsupported document type: {path.suffix}")
    if not text:
        raise ValueError(f"Document produced no text: {path}")
    return text


def _portable_source_path(path: Path) -> str:
    parts = path.parts
    position = next(
        (index for index, part in enumerate(parts) if part.casefold() == "knowledgebase"),
        None,
    )
    return Path(*parts[position:]).as_posix() if position is not None else path.as_posix()


def prepare_document(path: Path) -> BaselineDocument:
    """Flatten one document and create fixed 120-word windows with 20-word overlap."""

    words = flatten_document(path).split()
    source_path = _portable_source_path(path)
    step = CHUNK_SIZE_WORDS - OVERLAP_WORDS
    chunks: list[RetrievedChunk] = []
    for word_start in range(0, len(words), step):
        window = words[word_start : word_start + CHUNK_SIZE_WORDS]
        if not window:
            break
        content = " ".join(window)
        identity = f"baseline|{source_path}|{word_start}|{content}"
        chunk_id = "baseline-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        chunks.append(
            RetrievedChunk(
                id=chunk_id,
                content=content,
                title=path.stem,
                source_path=source_path,
            )
        )
        if word_start + CHUNK_SIZE_WORDS >= len(words):
            break
    if not chunks:
        raise ValueError(f"Document produced no baseline chunks: {path}")
    return BaselineDocument(path=path, chunks=tuple(chunks))


def prepare_corpus(root: Path = DEFAULT_ROOT) -> list[BaselineDocument]:
    """Prepare the complete baseline corpus and reject missing documents."""

    documents = [prepare_document(path) for path in discover_documents(root)]
    if not documents:
        raise ValueError(f"No supported documents found under: {root}")
    return documents


def corpus_fingerprint(documents: Sequence[BaselineDocument]) -> str:
    """Fingerprint ordered source paths, IDs, and content for repeatability evidence."""

    entries = (
        f"{document.path.as_posix()}|{chunk.id}|{chunk.content}"
        for document in documents
        for chunk in document.chunks
    )
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def build_baseline_index_schema(index_name: str) -> SearchIndex:
    """Create a vector-capable schema without semantic ranking configuration."""

    return SearchIndex(
        name=index_name,
        fields=[
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SearchableField(name="content", type=SearchFieldDataType.String),
            SearchableField(name="title", type=SearchFieldDataType.String),
            SimpleField(name="source_path", type=SearchFieldDataType.String, filterable=True),
            SimpleField(name="page_number", type=SearchFieldDataType.Int32),
            SimpleField(name="section", type=SearchFieldDataType.String),
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
    )


def embed_in_batches(
    chunks: Sequence[RetrievedChunk],
    openai: AzureOpenAIAdapter,
) -> list[list[float]]:
    """Embed chunks in bounded batches and validate every result."""

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
    documents: Sequence[BaselineDocument],
    settings: Settings,
    credential: TokenCredential,
) -> tuple[int, int]:
    """Upsert deterministic baseline chunks and remove stale baseline IDs."""

    if settings.azure_auth_mode != "entra":
        raise ValueError("Baseline ingestion supports only AZURE_AUTH_MODE=entra")
    if not settings.azure_search_endpoint:
        raise ValueError("AZURE_SEARCH_ENDPOINT is required for --upload")
    chunks = [chunk for document in documents for chunk in document.chunks]
    desired_ids = {chunk.id for chunk in chunks}
    if len(desired_ids) != len(chunks):
        raise ValueError("Baseline chunk IDs must be unique across the corpus")

    index_name = settings.azure_search_baseline_index
    index_client = SearchIndexClient(settings.azure_search_endpoint, credential)
    document_client = SearchClient(settings.azure_search_endpoint, index_name, credential)
    openai = AzureOpenAIAdapter.from_settings(settings, credential)
    search = AzureSearchAdapter(document_client)
    try:
        index_client.create_or_update_index(build_baseline_index_schema(index_name))
        vectors = embed_in_batches(chunks, openai)
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
                raise RuntimeError(f"Failed to remove stale baseline chunks: {', '.join(failed)}")
        return len(chunks), len(stale_ids)
    finally:
        search.close()
        openai.close()
        index_client.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare or upload the fixed-window vector-only baseline corpus."
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Reconcile the baseline Azure Search index. The default is a safe dry run.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the safe-by-default baseline ingestion command."""

    args = _build_parser().parse_args(argv)
    documents = prepare_corpus(args.root)
    chunk_count = sum(len(document.chunks) for document in documents)
    print(f"Mode: {'upload' if args.upload else 'dry-run'}")
    print(f"Documents: {len(documents)}")
    print(f"Chunks: {chunk_count}")
    print(f"Chunk policy: {CHUNK_SIZE_WORDS} words with {OVERLAP_WORDS}-word overlap")
    print("Chunk ID scope: baseline-<24-character SHA-256 prefix>")
    print(f"Embedding dimensions: {VECTOR_DIMENSIONS}")
    print(f"Embedding batch size: {EMBEDDING_BATCH_SIZE}")
    print("Target setting: AZURE_SEARCH_BASELINE_INDEX")
    print(f"Corpus fingerprint: {corpus_fingerprint(documents)}")
    for document in documents:
        print(f"- {document.path.as_posix()}: {len(document.chunks)} chunks")

    if not args.upload:
        print("No Azure calls were made. Add --upload to reconcile the baseline index.")
        return 0

    settings = get_settings()
    credential = DefaultAzureCredential()
    try:
        uploaded, removed = upload_corpus(documents, settings, credential)
    finally:
        credential.close()
    print(f"Uploaded chunks: {uploaded}")
    print(f"Removed stale chunks: {removed}")
    print(f"Azure Search index: {settings.azure_search_baseline_index}")
    print(f"Embedding deployment: {settings.azure_openai_embedding_deployment}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
