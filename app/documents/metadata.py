"""Strict, versioned metadata policy for the assignment knowledge base."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, cast

DEFAULT_MANIFEST_PATH = Path("metadata/documents.json")
MANIFEST_SCHEMA_VERSION = 1
EXPECTED_DOCUMENT_COUNT = 11
SUPPORTED_FILE_TYPES = frozenset({"pdf", "docx", "xlsx"})
_ENTRY_KEYS = frozenset(
    {
        "source_path",
        "title",
        "file_type",
        "department",
        "document_type",
        "version",
        "effective_from",
        "effective_to",
        "is_current",
        "allowed_groups",
    }
)


def normalize_source_path(value: str | Path) -> str:
    """Return a portable, knowledge-base-relative source path."""

    raw = str(value).replace("\\", "/")
    parts = PurePosixPath(raw).parts
    position = next(
        (index for index, part in enumerate(parts) if part.casefold() == "knowledgebase"),
        None,
    )
    if position is None:
        raise ValueError(f"Source path must be inside KnowledgeBase: {value}")
    normalized = PurePosixPath(*parts[position:]).as_posix()
    if ".." in PurePosixPath(normalized).parts:
        raise ValueError(f"Source path cannot traverse directories: {value}")
    return normalized


def _parse_date(value: object, field_name: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO date or null")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO date: {value}") from error


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    """Validated document-level metadata copied onto every searchable chunk."""

    source_path: str
    title: str
    file_type: str
    department: str
    document_type: str
    version: str
    effective_from: date | None
    effective_to: date | None
    is_current: bool
    allowed_groups: tuple[str, ...]

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> DocumentMetadata:
        """Validate one manifest entry without silently accepting unknown fields."""

        keys = frozenset(raw)
        if keys != _ENTRY_KEYS:
            missing = sorted(_ENTRY_KEYS - keys)
            extra = sorted(keys - _ENTRY_KEYS)
            raise ValueError(f"Invalid metadata fields; missing={missing}, extra={extra}")

        if not isinstance(raw["source_path"], str):
            raise ValueError("source_path must be a string")
        if not isinstance(raw["file_type"], str):
            raise ValueError("file_type must be a string")
        source_path = normalize_source_path(raw["source_path"])
        file_type = raw["file_type"].casefold()
        if file_type not in SUPPORTED_FILE_TYPES:
            raise ValueError(f"Unsupported metadata file_type: {file_type}")
        expected_file_type = PurePosixPath(source_path).suffix.removeprefix(".").casefold()
        if file_type != expected_file_type:
            raise ValueError(f"file_type {file_type} does not match source path {source_path}")

        text_field_names = ("title", "department", "document_type", "version")
        invalid_text_fields = sorted(
            name for name in text_field_names if not isinstance(raw[name], str)
        )
        if invalid_text_fields:
            raise ValueError(f"Metadata fields must be strings: {invalid_text_fields}")
        text_fields = {name: cast("str", raw[name]).strip() for name in text_field_names}
        empty_fields = sorted(name for name, value in text_fields.items() if not value)
        if empty_fields:
            raise ValueError(f"Metadata fields cannot be empty: {empty_fields}")

        raw_groups = raw["allowed_groups"]
        if not isinstance(raw_groups, list) or not raw_groups:
            raise ValueError("allowed_groups must be a non-empty list")
        if not all(isinstance(group, str) for group in raw_groups):
            raise ValueError("allowed_groups values must be strings")
        groups = tuple(sorted({cast("str", group).strip().casefold() for group in raw_groups}))
        if not all(groups):
            raise ValueError("allowed_groups cannot contain empty values")
        if len(groups) != len(raw_groups):
            raise ValueError("allowed_groups must contain unique normalized values")

        effective_from = _parse_date(raw["effective_from"], "effective_from")
        effective_to = _parse_date(raw["effective_to"], "effective_to")
        if effective_from and effective_to and effective_to < effective_from:
            raise ValueError("effective_to cannot be earlier than effective_from")
        if not isinstance(raw["is_current"], bool):
            raise ValueError("is_current must be a boolean")

        return cls(
            source_path=source_path,
            title=text_fields["title"],
            file_type=file_type,
            department=text_fields["department"],
            document_type=text_fields["document_type"],
            version=text_fields["version"],
            effective_from=effective_from,
            effective_to=effective_to,
            is_current=raw["is_current"],
            allowed_groups=groups,
        )


def load_document_manifest(
    path: Path = DEFAULT_MANIFEST_PATH,
) -> dict[str, DocumentMetadata]:
    """Load the exact assignment manifest and enforce version-family invariants."""

    raw = cast("object", json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "documents"}:
        raise ValueError("Manifest must contain only schema_version and documents")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"Unsupported manifest schema_version: {raw['schema_version']}")
    raw_documents = raw["documents"]
    if not isinstance(raw_documents, list) or len(raw_documents) != EXPECTED_DOCUMENT_COUNT:
        raise ValueError(f"Manifest must contain exactly {EXPECTED_DOCUMENT_COUNT} documents")

    documents: dict[str, DocumentMetadata] = {}
    for raw_document in raw_documents:
        if not isinstance(raw_document, dict):
            raise ValueError("Every manifest document must be an object")
        metadata = DocumentMetadata.from_mapping(cast("dict[str, Any]", raw_document))
        key = metadata.source_path.casefold()
        if key in documents:
            raise ValueError(f"Duplicate metadata source_path: {metadata.source_path}")
        documents[key] = metadata

    families: dict[str, list[DocumentMetadata]] = {}
    for metadata in documents.values():
        families.setdefault(metadata.document_type.casefold(), []).append(metadata)
    for document_type, family in families.items():
        if len(family) > 1 and sum(document.is_current for document in family) != 1:
            raise ValueError(
                f"Version family {document_type} must have exactly one current document"
            )
    return documents
