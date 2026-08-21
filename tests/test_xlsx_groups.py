"""Tests for bounded, multi-row spreadsheet evidence chunks."""

from pathlib import Path

import pytest

from ingestion.xlsx import extract_xlsx
from ingestion.xlsx_groups import group_workbook_sheets

WORKBOOK_PATH = Path("KnowledgeBase/Sales/Discounts.xlsx")


def test_real_discount_workbook_groups_each_small_sheet_as_one_context() -> None:
    groups = group_workbook_sheets(extract_xlsx(WORKBOOK_PATH))

    assert [group.sheet_name for group in groups] == [
        "Volume Discounts",
        "Term Discounts",
        "Special Programs",
        "Approval Thresholds",
    ]
    assert len({group.chunk_id for group in groups}) == 4


def test_groups_supply_all_core_004_rows_in_three_retrieval_units() -> None:
    groups = group_workbook_sheets(extract_xlsx(WORKBOOK_PATH))
    by_sheet = {group.sheet_name: group.text for group in groups}

    assert "Seat Count Tier=250–499 seats" in by_sheet["Volume Discounts"]
    assert "Discount %=0.2" in by_sheet["Volume Discounts"]
    assert "Billing Term=Annual (prepaid)" in by_sheet["Term Discounts"]
    assert "Discount %=0.15" in by_sheet["Term Discounts"]
    assert "Combined Discount Range=30% – 40%" in by_sheet["Approval Thresholds"]
    assert "Chief Revenue Officer + Finance Business Partner" in by_sheet["Approval Thresholds"]


def test_grouped_special_program_context_supports_core_010() -> None:
    groups = group_workbook_sheets(extract_xlsx(WORKBOOK_PATH))
    special_programs = next(
        group.text for group in groups if group.sheet_name == "Special Programs"
    )

    startup_label = "Program=Startup " + chr(0x2014) + " Year 1; Discount %=0.3"
    assert startup_label in special_programs
    assert "do not stack with volume or term discounts" in special_programs
    assert "annual re-verification" in special_programs


def test_large_sheet_windows_overlap_and_are_deterministic() -> None:
    workbook = extract_xlsx(WORKBOOK_PATH)

    first = group_workbook_sheets(workbook, max_rows=5, overlap_rows=2)
    second = group_workbook_sheets(workbook, max_rows=5, overlap_rows=2)
    volume = [group for group in first if group.sheet_name == "Volume Discounts"]

    assert [group.chunk_id for group in first] == [group.chunk_id for group in second]
    assert len(volume) > 1
    assert volume[0].last_row >= volume[1].first_row


@pytest.mark.parametrize(
    ("max_rows", "overlap_rows", "message"),
    [(1, 0, "at least 2"), (5, 5, "between 0 and max_rows - 1"), (5, -1, "between")],
)
def test_group_window_validation(max_rows: int, overlap_rows: int, message: str) -> None:
    workbook = extract_xlsx(WORKBOOK_PATH)

    with pytest.raises(ValueError, match=message):
        group_workbook_sheets(
            workbook,
            max_rows=max_rows,
            overlap_rows=overlap_rows,
        )
