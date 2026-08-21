"""Canonical Azure AI Search serialization for improved RAG chunks."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from app.rag.models import RetrievedChunk

SEARCH_CHUNK_FIELDS = (
    "id",
    "content",
    "content_hash",
    "document_id",
    "title",
    "source_path",
    "file_type",
    "department",
    "document_type",
    "version",
    "effective_from",
    "effective_to",
    "is_current",
    "page_number",
    "section",
    "sheet_name",
    "table_number",
    "row_number",
    "allowed_groups",
)


def _search_datetime(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def _result_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text).date()


def chunk_to_search_document(
    chunk: RetrievedChunk,
    vector: list[float],
) -> dict[str, object]:
    """Serialize one chunk and its vector into the Azure index contract."""

    return {
        "id": chunk.id,
        "content": chunk.content,
        "content_hash": chunk.content_hash,
        "document_id": chunk.document_id,
        "title": chunk.title,
        "source_path": chunk.source_path,
        "file_type": chunk.file_type,
        "department": chunk.department,
        "document_type": chunk.document_type,
        "version": chunk.version,
        "effective_from": _search_datetime(chunk.effective_from),
        "effective_to": _search_datetime(chunk.effective_to),
        "is_current": chunk.is_current,
        "page_number": chunk.page_number,
        "section": chunk.section,
        "sheet_name": chunk.sheet_name,
        "table_number": chunk.table_number,
        "row_number": chunk.row_number,
        "allowed_groups": list(chunk.allowed_groups),
        "content_vector": vector,
    }


def chunk_from_search_result(result: dict[str, Any]) -> RetrievedChunk:
    """Deserialize a Search result while retaining its ranking score."""

    def optional_text(field: str) -> str | None:
        value = result.get(field)
        return str(value) if value is not None else None

    def optional_int(field: str) -> int | None:
        value = result.get(field)
        return int(value) if value is not None else None

    raw_groups = result.get("allowed_groups") or ()
    return RetrievedChunk(
        id=str(result["id"]),
        content=str(result["content"]),
        title=str(result["title"]),
        source_path=str(result["source_path"]),
        page_number=optional_int("page_number"),
        section=optional_text("section"),
        score=float(result["@search.score"]) if result.get("@search.score") is not None else None,
        document_id=optional_text("document_id"),
        content_hash=optional_text("content_hash"),
        file_type=optional_text("file_type"),
        department=optional_text("department"),
        document_type=optional_text("document_type"),
        version=optional_text("version"),
        effective_from=_result_date(result.get("effective_from")),
        effective_to=_result_date(result.get("effective_to")),
        is_current=(bool(result["is_current"]) if result.get("is_current") is not None else None),
        sheet_name=optional_text("sheet_name"),
        table_number=optional_int("table_number"),
        row_number=optional_int("row_number"),
        allowed_groups=tuple(str(group) for group in raw_groups),
    )
