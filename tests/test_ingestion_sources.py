"""Tests for local-folder and Azure Blob ingestion source parity and safety."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ingestion.sources import AzureBlobSource, LocalFolderSource


@dataclass(frozen=True)
class _Blob:
    name: str
    size: int
    etag: str = '"etag"'


class _Download:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def readall(self) -> bytes:
        return self._payload


class _Container:
    def __init__(self, blobs: list[_Blob], payloads: dict[str, bytes]) -> None:
        self._blobs = blobs
        self._payloads = payloads
        self.downloaded: list[str] = []

    def list_blobs(self) -> list[_Blob]:
        return self._blobs

    def download_blob(self, blob: str) -> _Download:
        self.downloaded.append(blob)
        return _Download(self._payloads[blob])


def test_local_and_blob_sources_have_identical_logical_paths(tmp_path: Path) -> None:
    local_root = tmp_path / "KnowledgeBase"
    local_path = local_root / "Finance" / "ExpensePolicy.pdf"
    local_path.parent.mkdir(parents=True)
    local_path.write_bytes(b"policy")
    container = _Container(
        [_Blob("KnowledgeBase/Finance/ExpensePolicy.pdf", 6)],
        {"KnowledgeBase/Finance/ExpensePolicy.pdf": b"policy"},
    )

    local = LocalFolderSource(local_root).materialize()
    with AzureBlobSource(container).materialize() as blob:
        assert [source.logical_path for source in local.sources] == [
            source.logical_path for source in blob.sources
        ]
        assert blob.sources[0].local_path.read_bytes() == b"policy"
        staging_directory = blob.staging_directory

    assert staging_directory is not None
    assert not staging_directory.exists()


def test_sources_filter_unsupported_files_and_report_warnings(tmp_path: Path) -> None:
    local_root = tmp_path / "input"
    local_root.mkdir()
    (local_root / "policy.pdf").write_bytes(b"policy")
    (local_root / "notes.txt").write_text("notes", encoding="utf-8")
    container = _Container(
        [
            _Blob("policy.pdf", 6),
            _Blob("notes.txt", 5),
            _Blob("empty.docx", 0),
        ],
        {"policy.pdf": b"policy", "notes.txt": b"notes", "empty.docx": b""},
    )

    local = LocalFolderSource(local_root).materialize()
    with AzureBlobSource(container).materialize() as blob:
        assert [source.logical_path for source in local.sources] == ["KnowledgeBase/policy.pdf"]
        assert [source.logical_path for source in blob.sources] == ["KnowledgeBase/policy.pdf"]
        assert {(warning.code, warning.source) for warning in blob.warnings} == {
            ("empty", "KnowledgeBase/empty.docx"),
            ("unsupported", "KnowledgeBase/notes.txt"),
        }
        assert container.downloaded == ["policy.pdf"]

    assert [(warning.code, warning.source) for warning in local.warnings] == [
        ("unsupported", "KnowledgeBase/notes.txt")
    ]


def test_blob_download_that_is_empty_is_warned_and_not_materialized() -> None:
    container = _Container([_Blob("broken.xlsx", 10)], {"broken.xlsx": b""})

    with AzureBlobSource(container).materialize() as result:
        assert result.sources == ()
        assert [(warning.code, warning.source) for warning in result.warnings] == [
            ("empty", "KnowledgeBase/broken.xlsx")
        ]


def test_blob_path_traversal_and_unsafe_windows_paths_are_never_downloaded() -> None:
    unsafe_names = [
        "../outside.pdf",
        "/absolute.pdf",
        "Finance\\escape.pdf",
        "Finance/C:/escape.pdf",
        "Finance/CON.pdf",
    ]
    container = _Container(
        [_Blob(name, 10) for name in unsafe_names],
        {name: b"not downloaded" for name in unsafe_names},
    )

    with AzureBlobSource(container).materialize() as result:
        assert result.sources == ()
        assert len(result.warnings) == len(unsafe_names)
        assert {warning.code for warning in result.warnings} == {"unsafe_path"}
        assert container.downloaded == []
