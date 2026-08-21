"""Prepare or incrementally upload every supported assignment document."""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Literal, Protocol, cast

from azure.core.credentials import TokenCredential
from azure.core.exceptions import ServiceRequestError, ServiceResponseError
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient

from app.config import Settings, get_settings
from app.documents.metadata import DocumentMetadata, load_document_manifest
from app.rag.azure import AzureOpenAIAdapter, AzureSearchAdapter
from app.rag.models import (
    RetrievedChunk,
    deterministic_chunk_id,
    deterministic_document_id,
    sha256_text,
)
from app.rag.search_documents import SEARCH_CHUNK_FIELDS, chunk_from_search_result
from ingestion.docx import ingest_docx
from ingestion.pdf import ingest_pdf
from ingestion.sources import (
    SUPPORTED_SUFFIXES,
    AzureBlobSource,
    LocalFolderSource,
    SourceMaterialization,
    SourceProvider,
    SourceWarning,
)
from ingestion.xlsx import extract_xlsx, ingest_xlsx
from ingestion.xlsx_groups import group_workbook_sheets
from scripts.mvp_ingest import VECTOR_DIMENSIONS, build_index_schema

DEFAULT_ROOT = Path("KnowledgeBase")
EMBEDDING_BATCH_SIZE = 64
DEFAULT_MAX_WORKERS = 4
DEFAULT_RETRY_ATTEMPTS = 3
PREVIEW_CHARACTERS = 180
FailureStage = Literal["delete", "embedding_or_upload", "existing_index", "preparation"]


class _Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts in their input order."""


class _Indexer(Protocol):
    def index(
        self,
        chunks: Sequence[RetrievedChunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        """Upload one corresponding chunk and vector batch."""


class _DocumentClient(Protocol):
    def search(self, **kwargs: object) -> Sequence[Mapping[str, Any]]:
        """Return existing indexed documents."""

    def delete_documents(self, *, documents: list[dict[str, str]]) -> Sequence[object]:
        """Delete documents by ID."""


@dataclass(frozen=True, slots=True)
class PreparedDocument:
    """One source document and its normalized searchable chunks."""

    path: Path
    metadata: DocumentMetadata
    chunks: tuple[RetrievedChunk, ...]


@dataclass(frozen=True, slots=True)
class IngestionFailure:
    """One failed ingestion stage with the affected source or chunk IDs."""

    stage: FailureStage
    items: tuple[str, ...]
    error: str


@dataclass(frozen=True, slots=True)
class PreparationReport:
    """Prepared documents plus explicit source warnings and failures."""

    documents: tuple[PreparedDocument, ...]
    warnings: tuple[SourceWarning, ...]
    failures: tuple[IngestionFailure, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    """Observable result of one incremental Search reconciliation."""

    desired: int
    uploaded: int
    unchanged: int
    deleted: int
    retries: int
    failures: tuple[IngestionFailure, ...]

    @property
    def succeeded(self) -> bool:
        return not self.failures


class _RetryCounter:
    def __init__(self) -> None:
        self.value = 0
        self._lock = Lock()

    def increment(self) -> None:
        with self._lock:
            self.value += 1


def discover_documents(root: Path) -> list[Path]:
    """Return every supported knowledge file in deterministic path order."""

    with LocalFolderSource(root).materialize() as materialization:
        return [source.local_path for source in materialization.sources]


def _canonical_chunk(
    metadata: DocumentMetadata,
    *,
    content: str,
    locator: str,
    page_number: int | None = None,
    section: str | None = None,
    sheet_name: str | None = None,
    table_number: int | None = None,
    row_number: int | None = None,
) -> RetrievedChunk:
    document_id = deterministic_document_id(metadata.source_path)
    content_hash = sha256_text(content)
    return RetrievedChunk(
        id=deterministic_chunk_id(document_id, locator, content_hash),
        content=content,
        title=metadata.title,
        source_path=metadata.source_path,
        page_number=page_number,
        section=section,
        document_id=document_id,
        content_hash=content_hash,
        file_type=metadata.file_type,
        department=metadata.department,
        document_type=metadata.document_type,
        version=metadata.version,
        effective_from=metadata.effective_from,
        effective_to=metadata.effective_to,
        is_current=metadata.is_current,
        sheet_name=sheet_name,
        table_number=table_number,
        row_number=row_number,
        allowed_groups=metadata.allowed_groups,
    )


def prepare_document(
    path: Path,
    metadata: DocumentMetadata | None = None,
) -> PreparedDocument:
    """Convert a supported local or staged file into canonical Search chunks."""

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported document type: {path.suffix}")
    if metadata is None:
        manifest = load_document_manifest()
        logical_path = next(
            (candidate for candidate in manifest if path.as_posix().casefold().endswith(candidate)),
            None,
        )
        if logical_path is None:
            raise ValueError(f"No metadata exists for source document: {path}")
        metadata = manifest[logical_path]

    if suffix == ".pdf":
        chunks = tuple(
            _canonical_chunk(
                metadata,
                content=chunk.text,
                locator=f"pdf:{chunk.page_number}:{chunk.chunk_number}",
                page_number=chunk.page_number,
            )
            for chunk in ingest_pdf(path)
        )
    elif suffix == ".docx":
        chunks = tuple(
            _canonical_chunk(
                metadata,
                content=chunk.text,
                locator=f"docx:{chunk.block_number}:{chunk.chunk_number}",
                section=chunk.section,
                table_number=chunk.table_number,
                row_number=chunk.row_number,
            )
            for chunk in ingest_docx(path)
        )
    else:
        row_chunks = tuple(
            _canonical_chunk(
                metadata,
                content=chunk.text,
                locator=f"xlsx:{chunk.sheet_number}:{chunk.row_number}",
                section=f"{chunk.sheet_name} row {chunk.row_number}",
                sheet_name=chunk.sheet_name,
                table_number=chunk.table_number,
                row_number=chunk.row_number,
            )
            for chunk in ingest_xlsx(path)
        )
        group_chunks = tuple(
            _canonical_chunk(
                metadata,
                content=group.text,
                locator=(
                    f"xlsx-group:{group.sheet_number}:{group.group_number}:"
                    f"{group.first_row}:{group.last_row}"
                ),
                section=(f"{group.sheet_name} grouped rows {group.first_row}-{group.last_row}"),
                sheet_name=group.sheet_name,
                row_number=group.first_row,
            )
            for group in group_workbook_sheets(extract_xlsx(path))
        )
        chunks = row_chunks + group_chunks
    if not chunks:
        raise ValueError(f"Document produced no searchable chunks: {metadata.source_path}")
    return PreparedDocument(path=path, metadata=metadata, chunks=chunks)


def prepare_materialized_sources(
    materialization: SourceMaterialization,
) -> PreparationReport:
    """Run all materialized sources through one parser and metadata pipeline."""

    manifest = load_document_manifest()
    documents: list[PreparedDocument] = []
    failures: list[IngestionFailure] = []
    discovered: set[str] = set()
    for source in materialization.sources:
        key = source.logical_path.casefold()
        discovered.add(key)
        metadata = manifest.get(key)
        if metadata is None:
            failures.append(
                IngestionFailure("preparation", (source.logical_path,), "metadata is missing")
            )
            continue
        try:
            documents.append(prepare_document(source.local_path, metadata))
        except Exception as error:
            failures.append(IngestionFailure("preparation", (source.logical_path,), str(error)))

    for missing_key in sorted(set(manifest) - discovered):
        failures.append(
            IngestionFailure(
                "preparation",
                (manifest[missing_key].source_path,),
                "declared source is missing or was excluded",
            )
        )
    return PreparationReport(
        documents=tuple(documents),
        warnings=materialization.warnings,
        failures=tuple(failures),
    )


def prepare_corpus(root: Path = DEFAULT_ROOT) -> list[PreparedDocument]:
    """Prepare every local document and reject warnings or partial failures."""

    with LocalFolderSource(root).materialize() as materialization:
        report = prepare_materialized_sources(materialization)
    if report.failures:
        details = "; ".join(f"{failure.items}: {failure.error}" for failure in report.failures)
        raise ValueError(f"Knowledge base preparation failed: {details}")
    if not report.documents:
        raise ValueError(f"No supported documents found under: {root}")
    return list(report.documents)


def _is_transient(error: BaseException) -> bool:
    if isinstance(error, (ServiceRequestError, ServiceResponseError, TimeoutError)):
        return True
    status_code = getattr(error, "status_code", None)
    if status_code is None:
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
    return status_code in {408, 409, 429} or (
        isinstance(status_code, int) and 500 <= status_code < 600
    )


def _call_with_retry[T](
    operation: Callable[[], T],
    *,
    attempts: int,
    counter: _RetryCounter,
    sleep: Callable[[float], None],
) -> T:
    if attempts < 1:
        raise ValueError("retry attempts must be at least one")
    for attempt_number in range(1, attempts + 1):
        try:
            return operation()
        except Exception as error:
            if attempt_number == attempts or not _is_transient(error):
                raise
            counter.increment()
            sleep(0.25 * (2 ** (attempt_number - 1)))
    raise AssertionError("retry loop must return or raise")


def _validate_vectors(
    vectors: Sequence[Sequence[float]],
    expected_count: int,
) -> None:
    if len(vectors) != expected_count:
        raise ValueError("Azure OpenAI returned an unexpected embedding count")
    if any(len(vector) != VECTOR_DIMENSIONS for vector in vectors):
        raise ValueError(f"Every embedding must contain {VECTOR_DIMENSIONS} dimensions")


def _chunk_state(chunk: RetrievedChunk) -> tuple[object, ...]:
    return (
        chunk.content_hash,
        chunk.document_id,
        chunk.title,
        chunk.source_path,
        chunk.file_type,
        chunk.department,
        chunk.document_type,
        chunk.version,
        chunk.effective_from,
        chunk.effective_to,
        chunk.is_current,
        chunk.page_number,
        chunk.section,
        chunk.sheet_name,
        chunk.table_number,
        chunk.row_number,
        chunk.allowed_groups,
    )


def reconcile_chunks(
    chunks: Sequence[RetrievedChunk],
    *,
    document_client: _DocumentClient,
    embedder: _Embedder,
    indexer: _Indexer,
    batch_size: int = EMBEDDING_BATCH_SIZE,
    max_workers: int = DEFAULT_MAX_WORKERS,
    retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> ReconciliationReport:
    """Incrementally index changed chunks and delete stale IDs only after full success."""

    if batch_size < 1 or max_workers < 1:
        raise ValueError("batch_size and max_workers must be at least one")
    desired_by_id = {chunk.id: chunk for chunk in chunks}
    if len(desired_by_id) != len(chunks):
        raise ValueError("Chunk IDs must be unique across the complete corpus")
    counter = _RetryCounter()

    try:
        raw_existing = _call_with_retry(
            lambda: list(
                document_client.search(
                    search_text="*",
                    select=list(SEARCH_CHUNK_FIELDS),
                    top=1000,
                )
            ),
            attempts=retry_attempts,
            counter=counter,
            sleep=sleep,
        )
        existing = {
            str(result["id"]): chunk_from_search_result(dict(result)) for result in raw_existing
        }
    except Exception as error:
        return ReconciliationReport(
            len(chunks),
            0,
            0,
            0,
            counter.value,
            (IngestionFailure("existing_index", (), str(error)),),
        )

    unchanged_ids = {
        chunk_id
        for chunk_id, chunk in desired_by_id.items()
        if chunk_id in existing and _chunk_state(existing[chunk_id]) == _chunk_state(chunk)
    }
    pending = [chunk for chunk in chunks if chunk.id not in unchanged_ids]
    batches = [
        tuple(pending[start : start + batch_size]) for start in range(0, len(pending), batch_size)
    ]

    def process_batch(batch: tuple[RetrievedChunk, ...]) -> int:
        vectors = _call_with_retry(
            lambda: embedder.embed([chunk.content for chunk in batch]),
            attempts=retry_attempts,
            counter=counter,
            sleep=sleep,
        )
        _validate_vectors(vectors, len(batch))
        _call_with_retry(
            lambda: indexer.index(batch, vectors),
            attempts=retry_attempts,
            counter=counter,
            sleep=sleep,
        )
        return len(batch)

    uploaded = 0
    failures: list[IngestionFailure] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_batches = {executor.submit(process_batch, batch): batch for batch in batches}
        for future in as_completed(future_batches):
            batch = future_batches[future]
            try:
                uploaded += future.result()
            except Exception as error:
                failures.append(
                    IngestionFailure(
                        "embedding_or_upload",
                        tuple(chunk.id for chunk in batch),
                        str(error),
                    )
                )

    if failures:
        return ReconciliationReport(
            len(chunks),
            uploaded,
            len(unchanged_ids),
            0,
            counter.value,
            tuple(sorted(failures, key=lambda failure: failure.items)),
        )

    stale_ids = sorted(set(existing) - set(desired_by_id))
    if stale_ids:
        try:

            def delete_stale() -> None:
                results = document_client.delete_documents(
                    documents=[{"id": chunk_id} for chunk_id in stale_ids]
                )
                failed = [
                    str(getattr(result, "key", "<unknown>"))
                    for result in results
                    if not bool(getattr(result, "succeeded", False))
                ]
                if failed:
                    raise RuntimeError(f"Failed to remove stale Search chunks: {failed}")

            _call_with_retry(
                delete_stale,
                attempts=retry_attempts,
                counter=counter,
                sleep=sleep,
            )
        except Exception as error:
            return ReconciliationReport(
                len(chunks),
                uploaded,
                len(unchanged_ids),
                0,
                counter.value,
                (IngestionFailure("delete", tuple(stale_ids), str(error)),),
            )

    return ReconciliationReport(
        len(chunks),
        uploaded,
        len(unchanged_ids),
        len(stale_ids),
        counter.value,
        (),
    )


def upload_corpus(
    documents: Sequence[PreparedDocument],
    settings: Settings,
    credential: TokenCredential,
    *,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> ReconciliationReport:
    """Create the canonical index and safely reconcile the complete corpus."""

    if not settings.azure_search_endpoint:
        raise ValueError("AZURE_SEARCH_ENDPOINT is required for upload")
    chunks = [chunk for document in documents for chunk in document.chunks]
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
        return reconcile_chunks(
            chunks,
            document_client=cast(_DocumentClient, document_client),
            embedder=openai,
            indexer=search,
            max_workers=max_workers,
        )
    finally:
        search.close()
        openai.close()
        document_client.close()
        index_client.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--source", choices=("local", "blob"), default="local")
    parser.add_argument("--preview-limit", type=int, default=3)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Reconcile the complete corpus to Search. The default is a dry run.",
    )
    return parser


def _print_preparation(report: PreparationReport, preview_limit: int) -> None:
    chunks = [chunk for document in report.documents for chunk in document.chunks]
    print(f"Documents: {len(report.documents)}")
    print(f"Chunks: {len(chunks)}")
    for warning in report.warnings:
        print(f"WARNING [{warning.code}] {warning.message}")
    for failure in report.failures:
        print(f"FAILED [{failure.stage}] {', '.join(failure.items)}: {failure.error}")
    for document in report.documents:
        print(f"- {document.metadata.source_path}: {len(document.chunks)} chunks")
    for chunk in chunks[: max(preview_limit, 0)]:
        text = " ".join(chunk.content.split())[:PREVIEW_CHARACTERS]
        print(
            f"PREVIEW {chunk.id} | {chunk.source_path} | "
            f"page={chunk.page_number} section={chunk.section!r} | {text}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Run local or Blob ingestion with safe-by-default dry-run behavior."""

    args = _build_parser().parse_args(argv)
    if args.preview_limit < 0 or args.max_workers < 1:
        raise ValueError("preview-limit must be non-negative and max-workers must be positive")
    print(f"Mode: {'upload' if args.upload else 'dry-run'}")
    print(f"Source: {args.source}")

    settings: Settings | None = None
    credential: DefaultAzureCredential | None = None
    if args.source == "blob" or args.upload:
        settings = get_settings()
        credential = DefaultAzureCredential()
    try:
        provider: SourceProvider
        if args.source == "blob":
            assert settings is not None and credential is not None
            if not settings.azure_storage_account_url:
                raise ValueError("AZURE_STORAGE_ACCOUNT_URL is required for Blob ingestion")
            provider = AzureBlobSource.from_account_url(
                settings.azure_storage_account_url,
                settings.azure_storage_container,
                credential,
            )
        else:
            provider = LocalFolderSource(args.root)

        with provider.materialize() as materialization:
            report = prepare_materialized_sources(materialization)
            _print_preparation(report, args.preview_limit)
            if report.failures:
                print("No Search mutation was attempted because preparation was incomplete.")
                return 1
            if not args.upload:
                print("No Search mutation was made. Add --upload after reviewing the preview.")
                return 0
            assert settings is not None and credential is not None
            reconciliation = upload_corpus(
                report.documents,
                settings,
                credential,
                max_workers=args.max_workers,
            )
    finally:
        if credential is not None:
            credential.close()

    print(f"Uploaded chunks: {reconciliation.uploaded}")
    print(f"Unchanged chunks: {reconciliation.unchanged}")
    print(f"Removed stale chunks: {reconciliation.deleted}")
    print(f"Transient retries: {reconciliation.retries}")
    for failure in reconciliation.failures:
        print(f"FAILED [{failure.stage}] {', '.join(failure.items)}: {failure.error}")
    print(f"Azure Search index: {settings.azure_search_improved_index}")
    return 0 if reconciliation.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
