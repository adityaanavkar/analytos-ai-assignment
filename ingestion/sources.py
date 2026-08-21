"""Typed local-folder and Azure Blob inputs for the shared ingestion pipeline."""

from __future__ import annotations

import re
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import TracebackType
from typing import Literal, Protocol, cast

from azure.core.credentials import TokenCredential
from azure.storage.blob import BlobServiceClient

SUPPORTED_SUFFIXES = frozenset({".pdf", ".docx", ".xlsx"})
WarningCode = Literal["empty", "unsafe_path", "unsupported"]
SourceOrigin = Literal["blob", "local"]

_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)
_UNSAFE_WINDOWS_CHARACTER = re.compile(r'[<>:"|?*\x00-\x1f]')


@dataclass(frozen=True, slots=True)
class SourceWarning:
    """A source that was intentionally excluded from ingestion."""

    code: WarningCode
    source: str
    message: str


@dataclass(frozen=True, slots=True)
class MaterializedSource:
    """One supported source with a stable logical path and readable local file."""

    logical_path: str
    local_path: Path
    origin: SourceOrigin
    size_bytes: int
    etag: str | None = None


class SourceMaterialization:
    """Materialized sources and warnings with optional temporary-file ownership."""

    def __init__(
        self,
        sources: Iterable[MaterializedSource],
        warnings: Iterable[SourceWarning] = (),
        *,
        staging_directory: Path | None = None,
    ) -> None:
        self.sources = tuple(sources)
        self.warnings = tuple(warnings)
        self.staging_directory = staging_directory
        self._closed = False

    def close(self) -> None:
        """Remove any Blob staging directory owned by this result."""

        if self._closed:
            return
        if self.staging_directory is not None:
            shutil.rmtree(self.staging_directory, ignore_errors=True)
        self._closed = True

    def __enter__(self) -> SourceMaterialization:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


class SourceProvider(Protocol):
    """An input that can expose supported files through local paths."""

    def materialize(self) -> SourceMaterialization:
        """Return readable local files and any intentionally skipped sources."""


class _DownloadStream(Protocol):
    def readall(self) -> bytes:
        """Read the complete Blob payload."""


class _ContainerClient(Protocol):
    def list_blobs(self) -> Iterable[object]:
        """List Blob property objects."""

    def download_blob(self, blob: str) -> _DownloadStream:
        """Download one Blob by name."""


def _logical_path(relative_path: PurePosixPath, logical_root: str) -> str:
    root = logical_root.strip("/")
    parts = relative_path.parts
    if parts and parts[0].casefold() == root.casefold():
        parts = parts[1:]
    return PurePosixPath(root, *parts).as_posix()


def _portable_relative_path(path: Path) -> PurePosixPath:
    return PurePosixPath(*path.parts)


def _unsafe_component(component: str) -> bool:
    base_name = component.split(".", maxsplit=1)[0].upper()
    return (
        not component
        or component in {".", ".."}
        or component.endswith((" ", "."))
        or _UNSAFE_WINDOWS_CHARACTER.search(component) is not None
        or base_name in _WINDOWS_RESERVED_NAMES
    )


def _safe_blob_path(blob_name: str) -> PurePosixPath | None:
    """Validate a Blob name before using its components as a local path."""

    if not blob_name or "\\" in blob_name or blob_name.startswith("/"):
        return None
    raw_parts = blob_name.split("/")
    if any(_unsafe_component(part) for part in raw_parts):
        return None
    return PurePosixPath(*raw_parts)


def _warning(code: WarningCode, source: str, detail: str) -> SourceWarning:
    return SourceWarning(code=code, source=source, message=f"Skipped {source}: {detail}")


class LocalFolderSource:
    """Discover supported non-empty files beneath one local folder."""

    def __init__(self, root: Path, *, logical_root: str = "KnowledgeBase") -> None:
        self._root = root
        self._logical_root = logical_root

    def materialize(self) -> SourceMaterialization:
        """Return deterministic local files without copying or cloud access."""

        if not self._root.is_dir():
            raise FileNotFoundError(f"Source directory does not exist: {self._root}")
        resolved_root = self._root.resolve()
        sources: list[MaterializedSource] = []
        warnings: list[SourceWarning] = []

        for path in sorted(self._root.rglob("*"), key=lambda item: item.as_posix().casefold()):
            if not path.is_file():
                continue
            try:
                resolved_path = path.resolve(strict=True)
                relative = resolved_path.relative_to(resolved_root)
            except OSError, ValueError:
                warnings.append(
                    _warning(
                        "unsafe_path",
                        path.as_posix(),
                        "path resolves outside the source root",
                    )
                )
                continue

            logical_path = _logical_path(_portable_relative_path(relative), self._logical_root)
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                warnings.append(_warning("unsupported", logical_path, "unsupported file type"))
                continue
            size = resolved_path.stat().st_size
            if size == 0:
                warnings.append(_warning("empty", logical_path, "file is empty"))
                continue
            sources.append(
                MaterializedSource(
                    logical_path=logical_path,
                    local_path=resolved_path,
                    origin="local",
                    size_bytes=size,
                )
            )

        return SourceMaterialization(sources, warnings)


class AzureBlobSource:
    """Safely materialize supported Azure Blobs into an owned staging directory."""

    def __init__(
        self,
        container_client: _ContainerClient,
        *,
        logical_root: str = "KnowledgeBase",
    ) -> None:
        self._container_client = container_client
        self._logical_root = logical_root

    @classmethod
    def from_account_url(
        cls,
        account_url: str,
        container_name: str,
        credential: TokenCredential,
        *,
        logical_root: str = "KnowledgeBase",
    ) -> AzureBlobSource:
        """Create a provider using any Azure SDK-compatible token credential."""

        service_client = BlobServiceClient(account_url=account_url, credential=credential)
        container_client = cast(
            _ContainerClient,
            service_client.get_container_client(container_name),
        )
        return cls(container_client, logical_root=logical_root)

    def materialize(self) -> SourceMaterialization:
        """Download supported Blobs and report excluded entries without unsafe writes."""

        staging_directory = Path(tempfile.mkdtemp(prefix="analytos-ingestion-"))
        sources: list[MaterializedSource] = []
        warnings: list[SourceWarning] = []
        logical_paths: set[str] = set()
        try:
            blobs = sorted(
                self._container_client.list_blobs(),
                key=lambda blob: str(getattr(blob, "name", "")).casefold(),
            )
            for blob in blobs:
                blob_name = str(getattr(blob, "name", ""))
                relative_path = _safe_blob_path(blob_name)
                if relative_path is None:
                    warnings.append(
                        _warning("unsafe_path", blob_name or "[unnamed blob]", "unsafe Blob path")
                    )
                    continue

                logical_path = _logical_path(relative_path, self._logical_root)
                logical_key = logical_path.casefold()
                if relative_path.suffix.lower() not in SUPPORTED_SUFFIXES:
                    warnings.append(_warning("unsupported", logical_path, "unsupported file type"))
                    continue
                if logical_key in logical_paths:
                    warnings.append(
                        _warning("unsafe_path", blob_name, "duplicate logical destination")
                    )
                    continue
                size = int(getattr(blob, "size", 0) or 0)
                if size == 0:
                    warnings.append(_warning("empty", logical_path, "Blob is empty"))
                    continue

                payload = self._container_client.download_blob(blob_name).readall()
                if not payload:
                    warnings.append(_warning("empty", logical_path, "downloaded Blob is empty"))
                    continue
                destination = staging_directory.joinpath(*PurePosixPath(logical_path).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(payload)
                logical_paths.add(logical_key)
                raw_etag = getattr(blob, "etag", None)
                sources.append(
                    MaterializedSource(
                        logical_path=logical_path,
                        local_path=destination,
                        origin="blob",
                        size_bytes=len(payload),
                        etag=str(raw_etag) if raw_etag is not None else None,
                    )
                )
        except BaseException:
            shutil.rmtree(staging_directory, ignore_errors=True)
            raise

        return SourceMaterialization(
            sources,
            warnings,
            staging_directory=staging_directory,
        )
