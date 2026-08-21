"""Canonical enterprise-document metadata."""

from app.documents.metadata import (
    DEFAULT_MANIFEST_PATH,
    DocumentMetadata,
    load_document_manifest,
    normalize_source_path,
)

__all__ = [
    "DEFAULT_MANIFEST_PATH",
    "DocumentMetadata",
    "load_document_manifest",
    "normalize_source_path",
]
