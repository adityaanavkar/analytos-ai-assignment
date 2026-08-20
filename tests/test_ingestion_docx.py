"""Real-document tests for structure-preserving DOCX ingestion."""

from pathlib import Path

import pytest
from docx import Document

from ingestion.docx import extract_docx, ingest_docx

DOCX_CASES = [
    (Path("KnowledgeBase/Finance/TravelPolicy.docx"), 3, 13),
    (Path("KnowledgeBase/IT/PasswordPolicy.docx"), 1, 6),
    (Path("KnowledgeBase/Legal/NDA.docx"), 1, 5),
]


@pytest.mark.parametrize(("document_path", "table_count", "table_row_count"), DOCX_CASES)
def test_all_docx_files_preserve_paragraphs_and_every_table_row(
    document_path: Path,
    table_count: int,
    table_row_count: int,
) -> None:
    document = Document(str(document_path))
    blocks = extract_docx(document_path)
    paragraph_blocks = [block for block in blocks if block.kind != "table_row"]
    table_blocks = [block for block in blocks if block.kind == "table_row"]

    expected_paragraphs = [paragraph for paragraph in document.paragraphs if paragraph.text.strip()]
    assert len(paragraph_blocks) == len(expected_paragraphs)
    assert len({block.table_number for block in table_blocks}) == table_count
    assert len(table_blocks) == table_row_count
    assert [block.block_number for block in blocks] == list(range(1, len(blocks) + 1))
    assert all(block.source_path == document_path.as_posix() for block in blocks)


def test_travel_policy_keeps_table_in_document_order_and_section() -> None:
    blocks = extract_docx("KnowledgeBase/Finance/TravelPolicy.docx")
    air_heading = next(block for block in blocks if block.text == "3. Air Travel")
    first_air_table_row = next(
        block for block in blocks if block.kind == "table_row" and block.table_number == 1
    )
    hotel_heading = next(block for block in blocks if block.text == "4. Hotel Accommodations")

    assert air_heading.block_number < first_air_table_row.block_number < hotel_heading.block_number
    assert first_air_table_row.section == "3. Air Travel"
    assert first_air_table_row.table_headers == (
        "Flight Duration",
        "Individual Contributor / Manager",
        "Director & Above",
    )
    assert "Flight Duration: Under 6 hours" in blocks[first_air_table_row.block_number].text


@pytest.mark.parametrize(
    ("document_path", "expected_table_text"),
    [
        (Path("KnowledgeBase/Finance/TravelPolicy.docx"), "Nightly Cap: $350"),
        (Path("KnowledgeBase/IT/PasswordPolicy.docx"), "Standard: 12 characters"),
        (Path("KnowledgeBase/Legal/NDA.docx"), "Northwind Traders, Inc.:"),
    ],
)
def test_table_values_reach_searchable_chunks(
    document_path: Path,
    expected_table_text: str,
) -> None:
    chunks = ingest_docx(document_path)

    assert any(expected_table_text in chunk.text for chunk in chunks)
    assert all(chunk.section for chunk in chunks)
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)


@pytest.mark.parametrize(("document_path", "_table_count", "_table_row_count"), DOCX_CASES)
def test_chunk_ids_are_stable_across_repeated_ingestion(
    document_path: Path,
    _table_count: int,
    _table_row_count: int,
) -> None:
    first = ingest_docx(document_path, chunk_size_words=40, overlap_words=10)
    second = ingest_docx(document_path, chunk_size_words=40, overlap_words=10)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]


def test_docx_validation_rejects_missing_or_wrong_file_type() -> None:
    with pytest.raises(FileNotFoundError, match="DOCX does not exist"):
        extract_docx("KnowledgeBase/Finance/missing.docx")
    with pytest.raises(ValueError, match="Expected a .docx"):
        extract_docx("KnowledgeBase/Finance/ExpensePolicy.pdf")
