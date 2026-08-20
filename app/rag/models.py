"""Small public data model for the first working RAG path."""

from dataclasses import dataclass


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


RagAnswer = ChatResult
