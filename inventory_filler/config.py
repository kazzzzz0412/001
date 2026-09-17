"""How this particular inventory sheet is laid out.

Nobody's inventory sheet looks like anyone else's, so nothing about the
columns is hardcoded. A column is named either by the text in its header row
("仕入日") or by its spreadsheet letter ("C") for sheets whose headers are
merged, blank, or too creative to match on.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("inventory.json")

DEFAULT_COLUMNS = {
    "purchased_on": "仕入日",
    "price": "仕入価格",
    "condition": "状態",
}


@dataclass
class SheetConfig:
    header_row: int = 1
    """1-based row holding the column headers. Data starts on the next row."""

    key_column: str = "管理番号"
    """The column that identifies a row - the management number."""

    columns: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_COLUMNS))
    """field name -> header text or column letter."""

    review_column: str = ""
    """Optional column for a "check this" note. Empty disables the note."""

    date_format: str = "%Y/%m/%d"
    condition_aliases: dict[str, str] = field(default_factory=dict)

    confidence_threshold: float = 0.8
    """Below this, a cell is still written but flagged for human review."""

    overwrite: bool = False
    """False leaves cells that already have a value alone and reports them as
    conflicts, so a re-run can never silently clobber hand-entered data."""

    append_unknown: bool = True
    """Add a new row for a management number the sheet does not have yet."""

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> SheetConfig:
        if not path.exists():
            return cls()
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        defaults = cls()
        return cls(
            header_row=data.get("header_row", defaults.header_row),
            key_column=data.get("key_column", defaults.key_column),
            columns=data.get("columns") or dict(DEFAULT_COLUMNS),
            review_column=data.get("review_column", defaults.review_column),
            date_format=data.get("date_format", defaults.date_format),
            condition_aliases=data.get("condition_aliases") or {},
            confidence_threshold=data.get("confidence_threshold", defaults.confidence_threshold),
            overwrite=data.get("overwrite", defaults.overwrite),
            append_unknown=data.get("append_unknown", defaults.append_unknown),
        )

    def save(self, path: Path = DEFAULT_CONFIG_PATH) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
