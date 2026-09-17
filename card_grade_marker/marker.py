"""Detect the grade-chip row in a screenshot and highlight a single chip.

The screenshots this targets are PSA population ("鑑定分布データ") screens: a
horizontally scrolling row of rounded rectangles on a near-black background,
one chip per grade, the currently selected chip drawn with a white border.

Detection is deliberately geometric rather than OCR based:

1. Find pairs of horizontal bars (the top and bottom edges of a rounded
   rectangle) that share a centre and a width and sit 60-500 px apart.
2. Inside each candidate band, project the non-background pixels onto the x
   axis; contiguous columns are chips.
3. Keep the band that looks most like a chip row (several chips of near
   identical width at a regular pitch), preferring one that contains a chip
   with a white border, i.e. the app's own selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
from PIL import Image, ImageDraw

# Pixels this much brighter than the page background count as "ink".
INK_MARGIN = 12
# A border drawn at this luminance or above counts as the white selection ring.
WHITE_LEVEL = 200
# Bars shorter than this cannot be the edge of a chip.
MIN_BAR_LENGTH = 100
# Plausible chip heights, in pixels.
MIN_CHIP_HEIGHT = 60
MAX_CHIP_HEIGHT = 500
# Chips narrower than this are noise, not chips.
MIN_CHIP_WIDTH = 40
# Score given to a band holding a single chip; a real row always beats it.
LONE_CHIP_SCORE = 0.5
# Supersampling factor used when drawing the arrow, for clean diagonal edges.
SUPERSAMPLE = 4


@dataclass(frozen=True)
class Chip:
    """One grade chip, in image pixel coordinates."""

    x0: int
    x1: int
    y0: int
    y1: int
    selected: bool = False

    @property
    def width(self) -> int:
        return self.x1 - self.x0 + 1

    @property
    def height(self) -> int:
        return self.y1 - self.y0 + 1

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass(frozen=True)
class ChipRow:
    """The detected row of chips plus the page background colour."""

    y0: int
    y1: int
    chips: tuple[Chip, ...]
    background: tuple[int, int, int]

    @property
    def height(self) -> int:
        return self.y1 - self.y0 + 1

    def selected_index(self) -> int | None:
        for i, chip in enumerate(self.chips):
            if chip.selected:
                return i
        return None


@dataclass
class MarkerStyle:
    """Look of the generated marker."""

    arrow_color: tuple[int, int, int] = (255, 194, 60)
    fill_color: tuple[int, int, int] | None = None  # None -> sampled background
    side: str = "auto"  # auto | left | right
    ring: bool = False
    # Extra rows erased above and below the chip row: one number for both,
    # or (top, bottom).
    pad: int | tuple[int, int] | None = None
    # Arrow geometry, as multiples of the chip height.
    gap_ratio: float = 0.10
    head_length_ratio: float = 0.52
    head_half_ratio: float = 0.42
    shaft_half_ratio: float = 0.16
    shaft_length_ratio: float = 1.00


def _runs(mask: Sequence[bool] | np.ndarray, min_length: int = 1) -> list[tuple[int, int]]:
    """Return inclusive (start, end) spans of consecutive true values."""
    arr = np.asarray(mask, dtype=bool)
    if arr.size == 0:
        return []
    edges = np.diff(np.concatenate(([False], arr, [False])).astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1) - 1
    long_enough = (ends - starts + 1) >= min_length
    return list(zip(starts[long_enough].tolist(), ends[long_enough].tolist()))


def _background_color(rgb: np.ndarray, y0: int, y1: int) -> tuple[int, int, int]:
    """Most common colour of a horizontal slice of the image."""
    band = rgb[y0 : y1 + 1].astype(np.int32)
    # Pack each pixel into one integer; counting scalars beats counting triples.
    packed = (band[..., 0] << 16) | (band[..., 1] << 8) | band[..., 2]
    values, counts = np.unique(packed.ravel(), return_counts=True)
    best = int(values[counts.argmax()])
    return (best >> 16) & 0xFF, (best >> 8) & 0xFF, best & 0xFF


@dataclass
class _Bar:
    """A horizontal edge candidate: consecutive rows of long bright runs."""

    y0: int
    y1: int
    x0: int
    x1: int

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def width(self) -> int:
        return self.x1 - self.x0 + 1


def _horizontal_bars(lum: np.ndarray, threshold: float) -> list[_Bar]:
    bars: list[_Bar] = []
    current: _Bar | None = None
    for y in range(lum.shape[0]):
        spans = _runs(lum[y] >= threshold, MIN_BAR_LENGTH)
        if not spans:
            current = None
            continue
        x0 = min(s[0] for s in spans)
        x1 = max(s[1] for s in spans)
        if current is not None and current.y1 == y - 1:
            current.y1 = y
            current.x0 = min(current.x0, x0)
            current.x1 = max(current.x1, x1)
        else:
            current = _Bar(y, y, x0, x1)
            bars.append(current)
    return bars


def _candidate_bands(bars: Iterable[_Bar]) -> list[tuple[int, int]]:
    """Pair up bars that could be the top and bottom edge of the same row."""
    bars = list(bars)
    bands: list[tuple[int, int]] = []
    for i, top in enumerate(bars):
        for bottom in bars[i + 1 :]:
            height = bottom.y1 - top.y0 + 1
            if not MIN_CHIP_HEIGHT <= height <= MAX_CHIP_HEIGHT:
                continue
            if abs(top.center - bottom.center) > 20:
                continue
            if abs(top.width - bottom.width) > 30:
                continue
            bands.append((top.y0, bottom.y1))
    return bands


def _middle(x0: int, x1: int) -> tuple[int, int]:
    """Middle 60% of a span, away from the rounded corners of a chip."""
    inset = int((x1 - x0) * 0.2)
    return x0 + inset, x1 - inset


def _border_levels(lum: np.ndarray, x0: int, x1: int, y0: int, y1: int) -> tuple[float, float]:
    """Brightest pixel on the top and on the bottom edge of a candidate chip."""
    mx0, mx1 = _middle(x0, x1)
    edge = max(1, round((y1 - y0 + 1) * 0.03))
    top = float(lum[y0 : y0 + edge + 1, mx0 : mx1 + 1].max())
    bottom = float(lum[max(y0, y1 - edge) : y1 + 1, mx0 : mx1 + 1].max())
    return top, bottom


def _chips_in_band(lum: np.ndarray, bg_lum: float, y0: int, y1: int) -> list[tuple[int, int]]:
    """Columns of ink that are closed top and bottom, i.e. bordered boxes.

    Text glyphs also form column groups, so the border test is what keeps a
    heading or a row of labels from being mistaken for the chip row.
    """
    band = lum[y0 : y1 + 1]
    ink = (band >= bg_lum + INK_MARGIN).any(axis=0)
    chips = []
    for x0, x1 in _runs(ink, MIN_CHIP_WIDTH):
        top, bottom = _border_levels(lum, x0, x1, y0, y1)
        if top >= bg_lum + INK_MARGIN and bottom >= bg_lum + INK_MARGIN:
            chips.append((x0, x1))
    return chips


def _spread(values: Sequence[float]) -> float:
    if len(values) < 2 or max(values) <= 0:
        return 0.0
    return (max(values) - min(values)) / max(values)


def _band_score(columns: Sequence[tuple[int, int]]) -> float:
    """How much a band looks like a row of equally sized, equally spaced chips."""
    if not columns:
        return 0.0
    if len(columns) == 1:
        # A row scrolled down to one chip, or one this tool has already marked.
        # Worth keeping, but any real row of chips should outrank it.
        return LONE_CHIP_SCORE
    widths = [c[1] - c[0] + 1 for c in columns]
    # The chip at the right edge is usually clipped by the edge of the screen.
    full = widths[:-1] if len(widths) > 2 else widths
    lefts = [c[0] for c in columns]
    pitches = [b - a for a, b in zip(lefts, lefts[1:])]
    quality = (1.0 - _spread(full)) * (1.0 - _spread(pitches))
    return len(columns) * max(0.0, quality)


def _is_selected(lum: np.ndarray, x0: int, x1: int, y0: int, y1: int) -> bool:
    """A chip is the app's current selection when its border is drawn white.

    The label inside every chip is white too, so only the border is looked at.
    """
    top, bottom = _border_levels(lum, x0, x1, y0, y1)
    return top >= WHITE_LEVEL and bottom >= WHITE_LEVEL


def _build_row(
    rgb: np.ndarray,
    lum: np.ndarray,
    y0: int,
    y1: int,
    columns: Sequence[tuple[int, int]],
) -> ChipRow:
    chips = tuple(
        Chip(x0=x0, x1=x1, y0=y0, y1=y1, selected=_is_selected(lum, x0, x1, y0, y1))
        for x0, x1 in columns
    )
    return ChipRow(y0=y0, y1=y1, chips=chips, background=_background_color(rgb, y0, y1))


def detect_chip_row(image: Image.Image, band: tuple[int, int] | None = None) -> ChipRow:
    """Locate the grade-chip row.

    ``band`` forces an explicit (y0, y1) row instead of searching for one.
    """
    rgb = np.asarray(image.convert("RGB")).astype(np.int16)
    lum = rgb.mean(axis=2)
    height = lum.shape[0]

    page_bg = _background_color(rgb, 0, height - 1)
    bg_lum = float(np.mean(page_bg))

    if band is not None:
        y0, y1 = band
        columns = _chips_in_band(lum, bg_lum, y0, y1)
        if not columns:
            raise ValueError(f"no chips found in rows {y0}-{y1}")
        return _build_row(rgb, lum, y0, y1, columns)

    bars = _horizontal_bars(lum, WHITE_LEVEL) + _horizontal_bars(lum, bg_lum + INK_MARGIN)
    bands = _candidate_bands(bars)
    if not bands:
        raise ValueError(
            "no chip row found: pass an explicit band with --band Y0:Y1"
        )

    best: tuple[float, tuple[int, int], list[tuple[int, int]]] | None = None
    for y0, y1 in bands:
        columns = _chips_in_band(lum, bg_lum, y0, y1)
        score = _band_score(columns)
        if score <= 0:
            continue
        if any(_is_selected(lum, x0, x1, y0, y1) for x0, x1 in columns):
            score += 0.5
        if best is None or score > best[0]:
            best = (score, (y0, y1), columns)
    if best is None:
        raise ValueError(
            "no chip row found: pass an explicit band with --band Y0:Y1"
        )

    _, (y0, y1), columns = best
    return _build_row(rgb, lum, y0, y1, columns)


def _arrow_polygons(
    chip: Chip, width: int, style: MarkerStyle
) -> tuple[list[tuple[float, float]], tuple[float, float, float, float]]:
    """Arrow head polygon and shaft box, pointing at ``chip``."""
    h = chip.height
    gap = style.gap_ratio * h
    head_len = style.head_length_ratio * h
    head_half = style.head_half_ratio * h
    shaft_half = style.shaft_half_ratio * h
    length = head_len + style.shaft_length_ratio * h

    space_right = width - 1 - chip.x1
    space_left = chip.x0
    side = style.side
    if side == "auto":
        side = "right" if space_right >= space_left else "left"

    available = (space_right if side == "right" else space_left) - gap
    if available < head_len * 1.2:
        raise ValueError(
            f"not enough room for an arrow on the {side} of the chip "
            f"({available:.0f}px); try --side {'left' if side == 'right' else 'right'}"
        )
    length = min(length, available)

    cy = chip.center_y
    if side == "right":
        tip = chip.x1 + gap
        head = [(tip, cy), (tip + head_len, cy - head_half), (tip + head_len, cy + head_half)]
        shaft = (tip + head_len, cy - shaft_half, tip + length, cy + shaft_half)
    else:
        tip = chip.x0 - gap
        head = [(tip, cy), (tip - head_len, cy - head_half), (tip - head_len, cy + head_half)]
        shaft = (tip - length, cy - shaft_half, tip - head_len, cy + shaft_half)
    return head, shaft


def render_highlight(image: Image.Image, row: ChipRow, target: int, style: MarkerStyle) -> Image.Image:
    """Return a copy of ``image`` with only ``target`` visible and an arrow on it."""
    if not 0 <= target < len(row.chips):
        raise IndexError(f"chip index {target} out of range (0..{len(row.chips) - 1})")

    chip = row.chips[target]
    out = image.convert("RGB").copy()
    width, height = out.size

    if style.pad is None:
        pad_top = pad_bottom = max(2, round(row.height * 0.02))
    elif isinstance(style.pad, tuple):
        pad_top, pad_bottom = style.pad
    else:
        pad_top = pad_bottom = style.pad
    band_top = max(0, row.y0 - pad_top)
    band_bottom = min(height - 1, row.y1 + pad_bottom)
    fill = style.fill_color if style.fill_color is not None else row.background

    keep = image.convert("RGB").crop(
        (max(0, chip.x0 - 2), band_top, min(width, chip.x1 + 3), band_bottom + 1)
    )
    ImageDraw.Draw(out).rectangle((0, band_top, width, band_bottom), fill=fill)
    out.paste(keep, (max(0, chip.x0 - 2), band_top))

    head, shaft = _arrow_polygons(chip, width, style)

    s = SUPERSAMPLE
    overlay = Image.new("RGBA", (width * s, height * s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    color = style.arrow_color + (255,)
    draw.polygon([(x * s, y * s) for x, y in head], fill=color)
    draw.rectangle(tuple(v * s for v in shaft), fill=color)
    if style.ring:
        margin = max(4, round(chip.height * 0.05))
        box = (
            (chip.x0 - margin) * s,
            (chip.y0 - margin) * s,
            (chip.x1 + margin) * s,
            (chip.y1 + margin) * s,
        )
        draw.rounded_rectangle(
            box,
            radius=round(chip.height * 0.22) * s,
            outline=color,
            width=max(3, round(chip.height * 0.025)) * s,
        )
    overlay = overlay.resize((width, height), Image.LANCZOS)
    out.paste(overlay, (0, 0), overlay)
    return out


def _row_with_single_chip(
    image: Image.Image, row: ChipRow, span: tuple[int, int]
) -> ChipRow:
    """Replace a detected row's chips with one chip covering ``span``."""
    x0, x1 = span
    if x1 <= x0:
        raise ValueError("chip columns must be given as X0:X1 with X1 greater than X0")
    lum = np.asarray(image.convert("RGB")).astype(np.int16).mean(axis=2)
    chip = Chip(
        x0=x0,
        x1=x1,
        y0=row.y0,
        y1=row.y1,
        selected=_is_selected(lum, x0, x1, row.y0, row.y1),
    )
    return ChipRow(y0=row.y0, y1=row.y1, chips=(chip,), background=row.background)


def highlight_grade(
    image: Image.Image,
    target: int | None = None,
    style: MarkerStyle | None = None,
    band: tuple[int, int] | None = None,
    chip: tuple[int, int] | None = None,
) -> tuple[Image.Image, ChipRow, int]:
    """Detect the chip row and highlight one chip.

    ``target`` is a 0-based index from the left; ``None`` uses the chip the app
    itself has selected (the one with the white border). ``chip`` names the kept
    chip's columns outright, for screenshots where something overlaps a chip and
    the two are read as one.
    """
    style = style or MarkerStyle()
    row = detect_chip_row(image, band=band)
    if chip is not None:
        row = _row_with_single_chip(image, row, chip)
        return render_highlight(image, row, 0, style), row, 0
    if target is None:
        target = row.selected_index()
        if target is None:
            raise ValueError(
                "no chip is selected in this screenshot; choose one with --target N "
                f"(1..{len(row.chips)}, counted from the left)"
            )
    return render_highlight(image, row, target, style), row, target
