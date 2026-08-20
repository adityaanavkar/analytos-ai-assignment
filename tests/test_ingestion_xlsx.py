"""Real-workbook tests for structure-preserving XLSX ingestion."""

from pathlib import Path

import pytest

from ingestion.xlsx import chunk_workbook, extract_xlsx, ingest_xlsx

WORKBOOK_PATH = Path("KnowledgeBase/Sales/Discounts.xlsx")


def test_extract_xlsx_preserves_sheet_order_rows_and_blank_separators() -> None:
    workbook = extract_xlsx(WORKBOOK_PATH)

    assert workbook.workbook_name == "Discounts.xlsx"
    assert workbook.source_path == WORKBOOK_PATH.as_posix()
    assert [sheet.sheet_name for sheet in workbook.sheets] == [
        "Volume Discounts",
        "Term Discounts",
        "Special Programs",
        "Approval Thresholds",
    ]
    assert sum(len(sheet.rows) for sheet in workbook.sheets) == 56
    assert sum(row.kind == "blank" for sheet in workbook.sheets for row in sheet.rows) == 11
    assert sum(row.kind == "header" for sheet in workbook.sheets for row in sheet.rows) == 4

    volume = workbook.sheets[0]
    assert volume.rows[0].kind == "title"
    assert volume.rows[2].kind == "blank"
    assert all(cell.value is None for cell in volume.rows[2].cells)


def test_extract_xlsx_preserves_table_headers_values_and_formulas() -> None:
    workbook = extract_xlsx(WORKBOOK_PATH)
    volume = workbook.sheets[0]
    header = volume.rows[5]
    first_data_row = volume.rows[6]
    discounted_row = volume.rows[7]

    expected_headers = (
        "Seat Count Tier",
        "Min Seats",
        "Discount %",
        "Discounted Price ($/seat/mo)",
    )
    assert header.kind == "header"
    assert header.table_number == 1
    assert header.headers == expected_headers
    assert first_data_row.kind == "data"
    assert first_data_row.headers == expected_headers
    assert first_data_row.table_number == 1
    assert discounted_row.cells[3].value == "61.75"
    assert discounted_row.cells[3].formula == "=$C$4*(1-C8)"


def test_chunk_workbook_is_deterministic_and_repeats_table_context() -> None:
    workbook = extract_xlsx(WORKBOOK_PATH)
    first_run = chunk_workbook(workbook)
    second_run = ingest_xlsx(WORKBOOK_PATH)

    assert len(first_run) == 45
    assert [chunk.chunk_id for chunk in first_run] == [chunk.chunk_id for chunk in second_run]
    assert len({chunk.chunk_id for chunk in first_run}) == 45

    annual = next(
        chunk
        for chunk in first_run
        if chunk.sheet_name == "Term Discounts" and chunk.row_number == 6
    )
    assert annual.row_kind == "data"
    assert annual.table_number == 1
    assert annual.headers == (
        "Billing Term",
        "Discount %",
        "Illustrative Price ($/seat/mo)",
    )
    assert "Workbook: Discounts.xlsx" in annual.text
    assert "Sheet: Term Discounts" in annual.text
    assert "Billing Term=Annual (prepaid)" in annual.text
    assert "Discount %=0.15" in annual.text
    assert "Illustrative Price ($/seat/mo)=55.25" in annual.text
    assert "formula: ='Volume Discounts'!$C$4*(1-B6)" in annual.text


def test_extract_xlsx_rejects_missing_or_wrong_file_type(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="XLSX file does not exist"):
        extract_xlsx(tmp_path / "missing.xlsx")

    wrong_type = tmp_path / "discounts.csv"
    wrong_type.write_text("header,value\nexample,1", encoding="utf-8")
    with pytest.raises(ValueError, match=r"Expected a \.xlsx file"):
        extract_xlsx(wrong_type)
