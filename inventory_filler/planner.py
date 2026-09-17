"""Decide which cells to write, without touching a spreadsheet.

Everything that could damage an inventory sheet is decided here, in pure
functions over a plain grid of strings, so the rules - never clobber an
existing value, flag anything read with low confidence, match rows by
management number - are settled by tests rather than by a live sheet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import SheetConfig
from .records import StickerRecord, normalize_management_no, normalize_text

_COLUMN_LETTER = re.compile(r"^[A-Za-z]{1,3}$")

FIELD_LABELS = {
    "management_no": "管理番号",
    "purchased_on": "仕入日",
    "price": "価格",
    "condition": "状態",
}


def column_letter(index: int) -> str:
    """1-based column index -> spreadsheet letter (1 -> A, 27 -> AA)."""
    if index < 1:
        raise ValueError(f"column index must be 1-based, got {index}")
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def column_index(letters: str) -> int:
    """Spreadsheet letter -> 1-based column index."""
    index = 0
    for char in letters.upper():
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index


@dataclass
class CellEdit:
    row: int
    column: int
    value: str
    field_name: str
    management_no: str
    confidence: float
    new_row: bool = False

    @property
    def a1(self) -> str:
        return f"{column_letter(self.column)}{self.row}"


@dataclass
class Conflict:
    """A cell that already held a different value, left untouched."""

    row: int
    column: int
    field_name: str
    management_no: str
    existing: str
    proposed: str

    @property
    def a1(self) -> str:
        return f"{column_letter(self.column)}{self.row}"


@dataclass
class ReviewItem:
    management_no: str
    row: int
    field_name: str
    value: str
    confidence: float
    note: str = ""


@dataclass
class Plan:
    edits: list[CellEdit] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    review: list[ReviewItem] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.edits


def _cell(grid: list[list[str]], row: int, column: int) -> str:
    """Read a 1-based cell from a ragged grid; missing cells read as empty."""
    if row < 1 or row > len(grid):
        return ""
    line = grid[row - 1]
    if column < 1 or column > len(line):
        return ""
    return normalize_text(line[column - 1])


def resolve_columns(
    grid: list[list[str]], config: SheetConfig
) -> tuple[dict[str, int], list[str]]:
    """Map each configured field to a 1-based column index.

    A configured name is matched against the header row first, so a sheet with
    a header literally named "C" still wins over the column-letter fallback.
    """
    header = grid[config.header_row - 1] if len(grid) >= config.header_row else []
    headers = {normalize_text(text): i + 1 for i, text in enumerate(header) if normalize_text(text)}

    wanted = {"management_no": config.key_column, **config.columns}
    if config.review_column:
        wanted["_review"] = config.review_column

    resolved: dict[str, int] = {}
    missing: list[str] = []
    for field_name, name in wanted.items():
        name = normalize_text(name)
        if not name:
            continue
        if name in headers:
            resolved[field_name] = headers[name]
        elif _COLUMN_LETTER.match(name):
            resolved[field_name] = column_index(name)
        else:
            missing.append(name)
    return resolved, missing


def _index_rows(grid: list[list[str]], key_column: int, first_data_row: int) -> dict[str, int]:
    rows: dict[str, int] = {}
    for row in range(first_data_row, len(grid) + 1):
        key = normalize_management_no(_cell(grid, row, key_column))
        if key and key not in rows:
            rows[key] = row
    return rows


def _last_used_row(grid: list[list[str]]) -> int:
    for row in range(len(grid), 0, -1):
        if any(normalize_text(cell) for cell in grid[row - 1]):
            return row
    return 0


def build_plan(
    grid: list[list[str]], records: list[StickerRecord], config: SheetConfig
) -> Plan:
    """Work out every cell write for these records against this sheet."""
    resolved, missing = resolve_columns(grid, config)
    plan = Plan(missing_columns=missing)

    key_column = resolved.get("management_no")
    if key_column is None:
        plan.missing_columns.append(config.key_column)
        return plan

    first_data_row = config.header_row + 1
    existing = _index_rows(grid, key_column, first_data_row)
    next_row = max(_last_used_row(grid), config.header_row) + 1

    for record in records:
        key = normalize_management_no(record.key)
        if not key:
            plan.unmatched.append(record.source_image or "(管理番号未読取)")
            continue

        row = existing.get(key)
        is_new = row is None
        if is_new:
            if not config.append_unknown:
                plan.unmatched.append(key)
                continue
            row = next_row
            next_row += 1
            existing[key] = row
            plan.edits.append(
                CellEdit(
                    row=row,
                    column=key_column,
                    value=key,
                    field_name="management_no",
                    management_no=key,
                    confidence=record.management_no.confidence,
                    new_row=True,
                )
            )

        flagged: list[str] = []
        if record.management_no.confidence < config.confidence_threshold:
            plan.review.append(
                ReviewItem(
                    management_no=key,
                    row=row,
                    field_name="management_no",
                    value=key,
                    confidence=record.management_no.confidence,
                    note=record.management_no.note,
                )
            )
            flagged.append(FIELD_LABELS["management_no"])

        for field_name, value in record.fields().items():
            if field_name == "management_no":
                continue
            column = resolved.get(field_name)
            if column is None or value.is_blank:
                continue

            current = "" if is_new else _cell(grid, row, column)
            if current and current != value.value and not config.overwrite:
                plan.conflicts.append(
                    Conflict(
                        row=row,
                        column=column,
                        field_name=field_name,
                        management_no=key,
                        existing=current,
                        proposed=value.value,
                    )
                )
                continue

            # Flag on the reading's confidence, not on whether this run happened
            # to write the cell - otherwise a second run against an already
            # filled sheet would quietly shrink the row's review note.
            if value.confidence < config.confidence_threshold:
                plan.review.append(
                    ReviewItem(
                        management_no=key,
                        row=row,
                        field_name=field_name,
                        value=value.value,
                        confidence=value.confidence,
                        note=value.note,
                    )
                )
                flagged.append(FIELD_LABELS.get(field_name, field_name))

            if current == value.value:
                continue

            plan.edits.append(
                CellEdit(
                    row=row,
                    column=column,
                    value=value.value,
                    field_name=field_name,
                    management_no=key,
                    confidence=value.confidence,
                    new_row=is_new,
                )
            )

        review_column = resolved.get("_review")
        if flagged and review_column is not None:
            note = "要確認: " + "、".join(flagged)
            # Skip an identical note so re-running against an already-filled
            # sheet is a no-op rather than a rewrite of the same text.
            if (_cell(grid, row, review_column) if not is_new else "") != note:
                plan.edits.append(
                    CellEdit(
                        row=row,
                        column=review_column,
                        value=note,
                        field_name="_review",
                        management_no=key,
                        confidence=1.0,
                        new_row=is_new,
                    )
                )

    return plan
