"""Public data models shared by the baseline and improved RAG paths."""

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Literal


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """A searchable document fragment with enough provenance for a citation."""

    id: str
    content: str
    title: str
    source_path: str
    page_number: int | None = None
    section: str | None = None
    score: float | None = None
    document_id: str | None = None
    content_hash: str | None = None
    file_type: str | None = None
    department: str | None = None
    document_type: str | None = None
    version: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    is_current: bool | None = None
    sheet_name: str | None = None
    table_number: int | None = None
    row_number: int | None = None
    allowed_groups: tuple[str, ...] = ()


def sha256_text(value: str) -> str:
    """Return a full lowercase SHA-256 digest."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def deterministic_document_id(source_path: str) -> str:
    """Build a stable document ID from a normalized portable path."""

    return sha256_text(source_path.casefold())[:24]


def deterministic_chunk_id(
    document_id: str,
    parser_chunk_id: str,
    content_hash: str,
) -> str:
    """Build a stable chunk ID from document, parser location, and content."""

    return sha256_text(f"{document_id}|{parser_chunk_id}|{content_hash}")[:24]


@dataclass(frozen=True, slots=True)
class IndexedDocument:
    """One distinct source represented in the search index."""

    title: str
    source_path: str


@dataclass(frozen=True, slots=True)
class Citation:
    """A verified citation resolved from a retrieved chunk."""

    chunk_id: str
    source: str
    page: int | None = None
    section: str | None = None


@dataclass(frozen=True, slots=True)
class ChatResult:
    """Grounded answer returned to an API or UI layer."""

    answer: str
    citations: tuple[Citation, ...]
    retrieved_chunks: int
    status: Literal["answer", "clarification"] = "answer"
    clarification: str | None = None
    rewritten_query: str | None = None
    temporal_intent: str | None = None
    subqueries: tuple[str, ...] = ()


RagAnswer = ChatResult
