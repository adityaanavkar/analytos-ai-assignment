"""End-to-end and boundary tests for the first PDF ingestion slice."""

from pathlib import Path

import pytest

from ingestion.pdf import chunk_pages, extract_pdf, ingest_pdf

EXPENSE_POLICY = Path("KnowledgeBase/Finance/ExpensePolicy.pdf")


def test_expense_policy_extracts_with_page_provenance() -> None:
    pages = extract_pdf(EXPENSE_POLICY)

    assert [page.page_number for page in pages] == [1, 2]
    assert all(
        page.source_path.endswith("KnowledgeBase/Finance/ExpensePolicy.pdf") for page in pages
    )
    assert "Business Expense & Reimbursement Policy" in pages[0].text
    assert "Reimbursement Timeline" in pages[1].text
    assert "\x7f" not in "".join(page.text for page in pages)


def test_expense_policy_is_chunked_end_to_end_with_exact_overlap() -> None:
    chunks = ingest_pdf(EXPENSE_POLICY, chunk_size_words=80, overlap_words=20)

    assert len(chunks) > 2
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    assert all(0 < len(chunk.text.split()) <= 80 for chunk in chunks)

    for left, right in zip(chunks, chunks[1:], strict=False):
        if left.page_number == right.page_number:
            assert left.text.split()[-20:] == right.text.split()[:20]
            assert right.word_start == left.word_end - 20

    repeated_run = ingest_pdf(EXPENSE_POLICY, chunk_size_words=80, overlap_words=20)
    assert [chunk.chunk_id for chunk in repeated_run] == [chunk.chunk_id for chunk in chunks]


@pytest.mark.parametrize(
    ("chunk_size_words", "overlap_words"),
    [(0, 0), (10, -1), (10, 10), (10, 11)],
)
def test_chunking_rejects_invalid_window_settings(
    chunk_size_words: int,
    overlap_words: int,
) -> None:
    pages = extract_pdf(EXPENSE_POLICY)

    with pytest.raises(ValueError):
        chunk_pages(
            pages,
            chunk_size_words=chunk_size_words,
            overlap_words=overlap_words,
        )


def test_extract_pdf_rejects_missing_file() -> None:
    with pytest.raises(FileNotFoundError, match="PDF does not exist"):
        extract_pdf("KnowledgeBase/Finance/does-not-exist.pdf")
