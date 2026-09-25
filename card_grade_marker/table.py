"""Mark one grade in the population table the PSA app shows now.

The app used to lay grades out as a row of chips, one of them selected; it now
draws a table - グレード / 枚数 / クオリファイヤ, a header, one row per grade and
a 合計 row at the foot. Nothing in the table says which grade is yours, so the
row is named by position and the others are wiped, header and total kept.

The table is found from its own rules: the long vertical lines are its borders
and column dividers, the long horizontal ones its row separators, and the rows
are what lies between them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

from .marker import (
    SUPERSAMPLE,
    Chip,
    MarkerStyle,
    _arrow_polygons,
    _background_color,
    _runs,
)

# A pixel is part of the table's rules when it is this much brighter than the page.
RULE_MARGIN = 25
# A horizontal rule has to cross this much of the table.
RULE_COVERAGE = 0.9
# A rule thicker than this is a filled row, not a line.
MAX_RULE_HEIGHT = 8


@dataclass(frozen=True)
class TableRow:
    """One row of the table, in image pixel coordinates."""

    y0: int
    y1: int
    kind: str  # header | grade | total

    @property
    def height(self) -> int:
        return self.y1 - self.y0 + 1


@dataclass(frozen=True)
class GradeTable:
    """The table's frame and its rows."""

    x0: int
    x1: int
    dividers: tuple[tuple[int, int], ...]  # vertical rules between the columns
    rows: tuple[TableRow, ...]
    rules: tuple[tuple[int, int], ...]  # horizontal rules between the rows
    background: tuple[int, int, int]

    @property
    def grades(self) -> tuple[TableRow, ...]:
        return tuple(row for row in self.rows if row.kind == "grade")


def _longest_run(values: np.ndarray) -> tuple[int, int]:
    spans = _runs(values)
    return max(spans, key=lambda span: span[1] - span[0])


def find_table(image: Image.Image) -> GradeTable:
    """Locate the population table and the rows inside it."""
    rgb = np.asarray(image.convert("RGB")).astype(np.int16)
    height, width, _ = rgb.shape
    lum = rgb.mean(axis=2)
    page = _background_color(rgb, 0, height - 1)
    bright = lum >= np.mean(page) + RULE_MARGIN

    # The table's verticals run its whole height; nothing else in the screen does.
    counts = bright.sum(axis=0)
    if not counts.max():
        raise ValueError("no table found in this screenshot")
    verticals = _runs(counts >= counts.max() * 0.5)
    if len(verticals) < 2:
        raise ValueError("no table found in this screenshot")
    x0, x1 = verticals[0][0], verticals[-1][1]

    inside = bright[:, x0 : x1 + 1].sum(axis=1) >= (x1 - x0 + 1) * RULE_COVERAGE
    if x0 >= 12:
        # A rule of the table stops at its border; a divider drawn across the
        # whole screen, such as the one under the tab bar, does not.
        margin = bright[:, max(0, x0 - 10) : x0 - 2].any(axis=1)
        inside &= ~margin
    spans = _runs(inside)
    if len(spans) < 3:
        raise ValueError("no rows found in this table")

    rules = tuple(span for span in spans if span[1] - span[0] + 1 <= MAX_RULE_HEIGHT)
    filled = [span for span in spans if span[1] - span[0] + 1 > MAX_RULE_HEIGHT]

    # Rows are the gaps between the rules; a filled span is a row in its own
    # right, which is how the 合計 row at the foot reads.
    content = x1 - 2
    divider = verticals[len(verticals) // 2]
    rows: list[TableRow] = []
    for (_, end), (start, _) in zip(spans, spans[1:]):
        if end + 1 > start - 1:
            continue
        band = rgb[end + 1 : start, divider[1] + 1 : content]
        tint = _background_color(band, 0, band.shape[0] - 1) if band.size else page
        kind = "grade" if tint == page else "header"
        rows.append(TableRow(end + 1, start - 1, kind))
    for start, end in filled:
        rows.append(TableRow(start, end, "total"))
    rows.sort(key=lambda row: row.y0)

    return GradeTable(
        x0=x0,
        x1=x1,
        dividers=tuple(verticals[1:-1]),
        rows=tuple(rows),
        rules=rules,
        background=page,
    )


def _erase_spans(table: GradeTable, target: TableRow) -> list[tuple[int, int]]:
    """Rows to wipe, with the rules between them, as contiguous y ranges."""
    doomed = [row for row in table.grades if row is not target]
    if not doomed:
        return []
    spans: list[list[int]] = []
    for row in doomed:
        # Rows that only have a rule between them are wiped as one, so the rule
        # goes too; the rules either side of the kept row stay.
        if spans and row.y0 - spans[-1][1] - 1 <= MAX_RULE_HEIGHT + 2:
            spans[-1][1] = row.y1
        else:
            spans.append([row.y0, row.y1])
    return [(start, end) for start, end in spans]


def _count_end(rgb: np.ndarray, table: GradeTable, row: TableRow) -> int:
    """Right edge of the first thing written past the grade column."""
    start = table.dividers[-1][1] + 1 if table.dividers else table.x0
    band = rgb[row.y0 : row.y1 + 1, start : table.x1]
    if not band.size:
        return start
    ink = band.mean(axis=2).max(axis=0) >= np.mean(table.background) + 60
    spans = _runs(ink, 3)
    if not spans:
        return start
    # Clear of the glyphs, whose antialiased edges reach past the run.
    return start + spans[0][1] + round(row.height * 0.15)


def mark_table(
    image: Image.Image,
    table: GradeTable,
    target: int,
    style: MarkerStyle,
    mark: str = "ring",
) -> Image.Image:
    """Wipe every grade row but ``target`` and mark the one left.

    ``mark`` is "ring" for an outline around the row, or "arrow" for one drawn
    in the empty last column, pointing back at the count.
    """
    if mark not in {"ring", "arrow"}:
        raise ValueError(f"mark must be 'ring' or 'arrow', not {mark!r}")
    grades = table.grades
    if not 0 <= target < len(grades):
        raise IndexError(f"row {target} out of range (0..{len(grades) - 1})")
    kept = grades[target]

    out = image.convert("RGB").copy()
    rgb = np.asarray(out).astype(np.int16)
    draw = ImageDraw.Draw(out)

    # Each column keeps its own shade, so the wiped rows read as empty table.
    edges = [(table.x0, table.x0)] + list(table.dividers) + [(table.x1, table.x1)]
    for y0, y1 in _erase_spans(table, kept):
        for (_, left), (right, _) in zip(edges, edges[1:]):
            band = rgb[y0 : y1 + 1, left + 1 : right]
            if not band.size:
                continue
            fill = style.fill_color or _background_color(band, 0, band.shape[0] - 1)
            draw.rectangle((left + 1, y0, right - 1, y1), fill=fill)

    width, height = out.size
    scale = SUPERSAMPLE
    overlay = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    pen = ImageDraw.Draw(overlay)
    color = style.arrow_color + (255,)
    if mark == "ring":
        inset = max(2, round(kept.height * 0.06))
        pen.rounded_rectangle(
            (
                (table.x0 + inset) * scale,
                (kept.y0 + inset) * scale,
                (table.x1 - inset) * scale,
                (kept.y1 - inset) * scale,
            ),
            radius=round(kept.height * 0.22) * scale,
            outline=color,
            width=max(3, round(kept.height * 0.06)) * scale,
        )
    else:
        # The arrow starts just past the count and runs out along the row, over
        # the last column, which only ever holds a dash.
        pointed_at = Chip(
            x0=table.x0, x1=_count_end(rgb, table, kept), y0=kept.y0, y1=kept.y1
        )
        head, shaft = _arrow_polygons(pointed_at, table.x1 + 1, style)
        pen.polygon([(x * scale, y * scale) for x, y in head], fill=color)
        pen.rectangle(tuple(v * scale for v in shaft), fill=color)
    overlay = overlay.resize((width, height), Image.LANCZOS)
    out.paste(overlay, (0, 0), overlay)
    return out
