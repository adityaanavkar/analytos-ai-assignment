"""Tests for the strict canonical document metadata policy."""

import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.documents.metadata import DEFAULT_MANIFEST_PATH, load_document_manifest


def _manifest() -> dict[str, Any]:
    return cast(
        "dict[str, Any]",
        json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8")),
    )


def _write_manifest(tmp_path: Path, value: dict[str, Any]) -> Path:
    path = tmp_path / "documents.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_manifest_covers_all_documents_with_acl_and_provenance_metadata() -> None:
    metadata = load_document_manifest()

    assert len(metadata) == 11
    assert {item.department for item in metadata.values()} == {
        "Finance",
        "HR",
        "IT",
        "Legal",
        "Sales",
    }
    assert all(item.allowed_groups for item in metadata.values())
    assert all(item.file_type == Path(item.source_path).suffix[1:] for item in metadata.values())
    assert all(item.version and item.document_type for item in metadata.values())


def test_manifest_classifies_current_and_historical_pricing() -> None:
    metadata = load_document_manifest()
    pricing = sorted(
        (item for item in metadata.values() if item.document_type == "pricing_rate_card"),
        key=lambda item: item.source_path,
    )

    assert [item.version for item in pricing] == ["1.4", "1.0"]
    assert [item.is_current for item in pricing] == [False, True]
    assert pricing[0].effective_to is not None
    assert pricing[1].effective_from is not None


def test_manifest_rejects_unknown_schema_version(tmp_path: Path) -> None:
    raw = _manifest()
    raw["schema_version"] = 2

    with pytest.raises(ValueError, match="schema_version"):
        load_document_manifest(_write_manifest(tmp_path, raw))


def test_manifest_rejects_duplicate_source_path(tmp_path: Path) -> None:
    raw = _manifest()
    raw["documents"][1]["source_path"] = raw["documents"][0]["source_path"]
    raw["documents"][1]["file_type"] = raw["documents"][0]["file_type"]

    with pytest.raises(ValueError, match="Duplicate"):
        load_document_manifest(_write_manifest(tmp_path, raw))


def test_manifest_rejects_multiple_current_versions(tmp_path: Path) -> None:
    raw = _manifest()
    pricing_2025 = next(
        item for item in raw["documents"] if item["source_path"].endswith("Pricing2025.pdf")
    )
    pricing_2025["is_current"] = True

    with pytest.raises(ValueError, match="exactly one current"):
        load_document_manifest(_write_manifest(tmp_path, raw))


def test_manifest_rejects_missing_or_unknown_fields(tmp_path: Path) -> None:
    raw = _manifest()
    del raw["documents"][0]["department"]
    raw["documents"][0]["unexpected"] = "value"

    with pytest.raises(ValueError, match="Invalid metadata fields"):
        load_document_manifest(_write_manifest(tmp_path, raw))


def test_manifest_rejects_coerced_metadata_types(tmp_path: Path) -> None:
    raw = _manifest()
    raw["documents"][0]["version"] = 5.1

    with pytest.raises(ValueError, match="must be strings"):
        load_document_manifest(_write_manifest(tmp_path, raw))
