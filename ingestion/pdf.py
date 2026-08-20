"""Small, deterministic PDF ingestion slice used by the baseline pipeline."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    """Text and provenance extracted from one PDF page."""

    source_path: str
    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class TextChunk:
    """A fixed-size word window with enough provenance for later citations."""

    chunk_id: str
    source_path: str
    page_number: int
    chunk_number: int
    word_start: int
    word_end: int
    text: str


def _normalise_text(text: str) -> str:
    """Remove extraction noise while preserving paragraphs and list meaning."""

    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x7f", "- ")
    text = "".join(
        character
        for character in text
        if character in "\n\t" or unicodedata.category(character) != "Cc"
    )
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def extract_pdf(path: str | Path) -> list[ExtractedPage]:
    """Extract non-empty pages from a local PDF without contacting Azure."""

    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF does not exist: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, received: {pdf_path.name}")

    reader = PdfReader(pdf_path)
    if reader.is_encrypted:
        raise ValueError(f"Encrypted PDFs are not supported: {pdf_path.name}")

    source_path = pdf_path.as_posix()
    pages: list[ExtractedPage] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = _normalise_text(page.extract_text() or "")
        if text:
            pages.append(
                ExtractedPage(
                    source_path=source_path,
                    page_number=page_number,
                    text=text,
                )
            )
    return pages


def chunk_pages(
    pages: list[ExtractedPage],
    *,
    chunk_size_words: int = 120,
    overlap_words: int = 20,
) -> list[TextChunk]:
    """Split each page into deterministic word windows with exact overlap."""

    if chunk_size_words <= 0:
        raise ValueError("chunk_size_words must be greater than zero")
    if overlap_words < 0 or overlap_words >= chunk_size_words:
        raise ValueError("overlap_words must be non-negative and smaller than chunk_size_words")

    step = chunk_size_words - overlap_words
    chunks: list[TextChunk] = []
    for page in pages:
        words = page.text.split()
        for chunk_number, word_start in enumerate(range(0, len(words), step), start=1):
            window = words[word_start : word_start + chunk_size_words]
            if not window:
                break
            text = " ".join(window)
            identity = f"{page.source_path}|{page.page_number}|{chunk_number}|{word_start}|{text}"
            chunks.append(
                TextChunk(
                    chunk_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
                    source_path=page.source_path,
                    page_number=page.page_number,
                    chunk_number=chunk_number,
                    word_start=word_start,
                    word_end=word_start + len(window),
                    text=text,
                )
            )
            if word_start + chunk_size_words >= len(words):
                break
    return chunks


def ingest_pdf(
    path: str | Path,
    *,
    chunk_size_words: int = 120,
    overlap_words: int = 20,
) -> list[TextChunk]:
    """Run the local PDF extraction and chunking stages end to end."""

    return chunk_pages(
        extract_pdf(path),
        chunk_size_words=chunk_size_words,
        overlap_words=overlap_words,
    )
