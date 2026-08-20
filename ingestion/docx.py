"""Structure-preserving DOCX extraction and deterministic MVP chunking."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

BlockKind = Literal["title", "heading", "paragraph", "list", "table_row"]


@dataclass(frozen=True, slots=True)
class DocxBlock:
    """One ordered Word document block with its structural context."""

    source_path: str
    block_number: int
    kind: BlockKind
    text: str
    section: str | None
    table_number: int | None = None
    row_number: int | None = None
    table_headers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DocxChunk:
    """A searchable word window linked back to its source block."""

    chunk_id: str
    source_path: str
    chunk_number: int
    block_number: int
    kind: BlockKind
    text: str
    section: str | None
    table_number: int | None = None
    row_number: int | None = None


def _normalise_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(
        character
        for character in text
        if character in "\n\t" or unicodedata.category(character) != "Cc"
    )
    return re.sub(r"\s+", " ", text).strip()


def _portable_source_path(path: Path) -> str:
    parts = path.parts
    knowledge_base_position = next(
        (position for position, part in enumerate(parts) if part.lower() == "knowledgebase"),
        None,
    )
    if knowledge_base_position is not None:
        return Path(*parts[knowledge_base_position:]).as_posix()
    return path.as_posix()


def _paragraph_kind(paragraph: Paragraph) -> BlockKind:
    style_name = paragraph.style.name.lower() if paragraph.style else ""
    if style_name == "title":
        return "title"
    if style_name.startswith("heading"):
        return "heading"
    if "list" in style_name:
        return "list"
    return "paragraph"


def _table_row_text(headers: tuple[str, ...], values: tuple[str, ...], row_number: int) -> str:
    if row_number == 1:
        return "Table headers: " + " | ".join(header or "[blank]" for header in headers)
    cells = [
        f"{header or f'Column {position}'}: {value or '[blank]'}"
        for position, (header, value) in enumerate(zip(headers, values, strict=True), start=1)
    ]
    return " | ".join(cells)


def extract_docx(path: str | Path) -> list[DocxBlock]:
    """Extract paragraphs and tables in their original document order."""

    docx_path = Path(path)
    if not docx_path.is_file():
        raise FileNotFoundError(f"DOCX does not exist: {docx_path}")
    if docx_path.suffix.lower() != ".docx":
        raise ValueError(f"Expected a .docx file, received: {docx_path.name}")

    document = Document(str(docx_path))
    source_path = _portable_source_path(docx_path)
    blocks: list[DocxBlock] = []
    current_section: str | None = None
    table_number = 0

    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            text = _normalise_text(item.text)
            if not text:
                continue
            kind = _paragraph_kind(item)
            if kind in {"title", "heading"}:
                current_section = text
            blocks.append(
                DocxBlock(
                    source_path=source_path,
                    block_number=len(blocks) + 1,
                    kind=kind,
                    text=text,
                    section=current_section,
                )
            )
            continue

        if isinstance(item, Table):
            table_number += 1
            rows = [tuple(_normalise_text(cell.text) for cell in row.cells) for row in item.rows]
            if not rows:
                continue
            headers = rows[0]
            for row_number, values in enumerate(rows, start=1):
                blocks.append(
                    DocxBlock(
                        source_path=source_path,
                        block_number=len(blocks) + 1,
                        kind="table_row",
                        text=_table_row_text(headers, values, row_number),
                        section=current_section,
                        table_number=table_number,
                        row_number=row_number,
                        table_headers=headers,
                    )
                )

    return blocks


def chunk_docx_blocks(
    blocks: list[DocxBlock],
    *,
    chunk_size_words: int = 160,
    overlap_words: int = 30,
) -> list[DocxChunk]:
    """Chunk each semantic block independently so sections and tables never mix."""

    if chunk_size_words <= 0:
        raise ValueError("chunk_size_words must be greater than zero")
    if overlap_words < 0 or overlap_words >= chunk_size_words:
        raise ValueError("overlap_words must be non-negative and smaller than chunk_size_words")

    step = chunk_size_words - overlap_words
    chunks: list[DocxChunk] = []
    for block in blocks:
        words = block.text.split()
        for word_start in range(0, len(words), step):
            window = words[word_start : word_start + chunk_size_words]
            if not window:
                break
            text = " ".join(window)
            identity = f"docx|{block.source_path}|{block.block_number}|{word_start}|{text}"
            chunks.append(
                DocxChunk(
                    chunk_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
                    source_path=block.source_path,
                    chunk_number=len(chunks) + 1,
                    block_number=block.block_number,
                    kind=block.kind,
                    text=text,
                    section=block.section,
                    table_number=block.table_number,
                    row_number=block.row_number,
                )
            )
            if word_start + chunk_size_words >= len(words):
                break
    return chunks


def ingest_docx(
    path: str | Path,
    *,
    chunk_size_words: int = 160,
    overlap_words: int = 30,
) -> list[DocxChunk]:
    """Run ordered Word extraction and structure-preserving chunking end to end."""

    return chunk_docx_blocks(
        extract_docx(path),
        chunk_size_words=chunk_size_words,
        overlap_words=overlap_words,
    )
