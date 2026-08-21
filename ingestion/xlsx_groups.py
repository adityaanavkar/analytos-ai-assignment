"""Grouped spreadsheet contexts for questions that span multiple rows."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from ingestion.xlsx import ExtractedWorkbook, SpreadsheetChunk, chunk_workbook


@dataclass(frozen=True, slots=True)
class SpreadsheetGroupChunk:
    """A bounded window of rows from one worksheet."""

    chunk_id: str
    source_path: str
    workbook_name: str
    sheet_name: str
    sheet_number: int
    group_number: int
    first_row: int
    last_row: int
    text: str


def group_workbook_sheets(
    workbook: ExtractedWorkbook,
    *,
    max_rows: int = 20,
    overlap_rows: int = 2,
) -> list[SpreadsheetGroupChunk]:
    """Create deterministic bounded sheet windows with row-level provenance.

    Small sheets become a single context chunk, which lets one retrieval hit
    carry all rows needed for cross-row calculations and range lookups.
    Larger sheets use overlapping windows so the index remains scalable.
    """

    if max_rows < 2:
        raise ValueError("max_rows must be at least 2")
    if not 0 <= overlap_rows < max_rows:
        raise ValueError("overlap_rows must be between 0 and max_rows - 1")

    row_chunks = chunk_workbook(workbook)
    by_sheet: dict[int, list[SpreadsheetChunk]] = {
        sheet.sheet_number: [] for sheet in workbook.sheets
    }
    for chunk in row_chunks:
        sheet_number = next(
            sheet.sheet_number for sheet in workbook.sheets if sheet.sheet_name == chunk.sheet_name
        )
        by_sheet[sheet_number].append(chunk)

    groups: list[SpreadsheetGroupChunk] = []
    step = max_rows - overlap_rows
    for sheet in workbook.sheets:
        rows = by_sheet[sheet.sheet_number]
        start = 0
        group_number = 1
        while start < len(rows):
            window = rows[start : start + max_rows]
            if not window:
                continue
            text = "\n\n".join(chunk.text for chunk in window)
            identity = json.dumps(
                {
                    "source_path": sheet.source_path,
                    "sheet_number": sheet.sheet_number,
                    "sheet_name": sheet.sheet_name,
                    "group_number": group_number,
                    "first_row": window[0].row_number,
                    "last_row": window[-1].row_number,
                    "text": text,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            groups.append(
                SpreadsheetGroupChunk(
                    chunk_id=hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
                    source_path=sheet.source_path,
                    workbook_name=sheet.workbook_name,
                    sheet_name=sheet.sheet_name,
                    sheet_number=sheet.sheet_number,
                    group_number=group_number,
                    first_row=window[0].row_number,
                    last_row=window[-1].row_number,
                    text=text,
                )
            )
            if start + max_rows >= len(rows):
                break
            start += step
            group_number += 1
    return groups
