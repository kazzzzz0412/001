"""Lay a listing title over a photo of cards without covering the artwork.

The caption style is the one marketplace listings use: heavy white gothic
Japanese text inside a thick red outline. Text goes in the empty bands above
and below the cards, so the artwork itself stays visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from PIL import Image

from card_lettering import LetterStyle, find_font, fit_size, line_image

# A pixel counts as artwork when this saturated and this bright.
ART_SATURATION = 0.28
ART_VALUE = 70
# A row belongs to the artwork when this much of its width is artwork.
ART_ROW_COVERAGE = 0.12
# Rows closer together than this belong to the same band.
ART_ROW_GAP = 30


@dataclass(frozen=True)
class TitleLines:
    """The title, split into the three places it is drawn."""

    top: str = ""
    main: str = ""
    bottom: str = ""

    def __bool__(self) -> bool:
        return bool(self.top or self.main or self.bottom)


@dataclass
class TitleStyle(LetterStyle):
    """Where the caption sits. Sizes scale with the photo."""

    # Widest each line may be, as a fraction of the photo width.
    main_width: float = 0.92
    top_width: float = 0.40
    bottom_width: float = 0.90
    # Tallest each line may be, as a fraction of the photo height.
    main_cap: float = 0.150
    top_cap: float = 0.072
    bottom_cap: float = 0.115
    # Gaps: from the artwork, between the two top lines, and from the edges.
    art_gap: float = 0.020
    line_gap: float = 0.014
    side_margin: float = 0.06


def split_title(title: str) -> TitleLines:
    """Split a title into a small top line, a big main line and a bottom line.

    The main line is what the listing is about, so it takes the middle words and
    is drawn largest; the first word becomes a small tag above it and whatever
    is left runs along the bottom. Words keep their spaces, which are drawn
    wider than the gap between characters.
    """
    words = title.split()
    if not words:
        return TitleLines()
    if len(words) == 1:
        return TitleLines(main=words[0])
    if len(words) == 2:
        return TitleLines(main=words[0], bottom=words[1])
    if len(words) == 3:
        return TitleLines(top=words[0], main=words[1], bottom=words[2])
    return TitleLines(top=words[0], main=" ".join(words[1:3]), bottom=" ".join(words[3:]))


def _row_bands(on: np.ndarray, gap: int) -> list[tuple[int, int]]:
    rows = np.flatnonzero(on)
    if rows.size == 0:
        return []
    bands: list[tuple[int, int]] = []
    start = previous = int(rows[0])
    for y in rows[1:]:
        y = int(y)
        if y > previous + gap:
            bands.append((start, previous))
            start = y
        previous = y
    bands.append((start, previous))
    return bands


def find_artwork_band(image: Image.Image) -> tuple[int, int]:
    """Rows spanned by the card artwork: the tallest band of colourful pixels.

    Slab labels and their red header are colourful too, but they only make thin
    bands, so text may cross them - it is the card faces that must stay clear.
    """
    rgb = np.asarray(image.convert("RGB")).astype(np.int16)
    height, width, _ = rgb.shape
    high = rgb.max(axis=2)
    low = rgb.min(axis=2)
    saturation = np.where(high > 0, (high - low) / np.maximum(high, 1), 0)
    colorful = (saturation > ART_SATURATION) & (high > ART_VALUE)

    coverage = colorful.sum(axis=1) / width
    bands = _row_bands(coverage > ART_ROW_COVERAGE, ART_ROW_GAP)
    if not bands:
        raise ValueError("no card artwork found in this photo")
    y0, y1 = max(bands, key=lambda band: band[1] - band[0])
    return y0, min(y1, height - 1)


@dataclass(frozen=True)
class _Placed:
    image: Image.Image
    x: int
    y: int


def _place_top_lines(
    lines: TitleLines,
    font_path: str,
    style: TitleStyle,
    size: tuple[int, int],
    band: tuple[int, int],
) -> list[_Placed]:
    width, height = size
    top_limit, bottom_limit = band
    room = bottom_limit - top_limit
    if room <= 0:
        return []

    gap = round(height * style.line_gap)
    art_gap = round(height * style.art_gap)
    placed: list[Image.Image] = []

    main = None
    if lines.main:
        main_size = fit_size(
            lines.main,
            font_path,
            style,
            round(width * style.main_width),
            round(height * style.main_cap),
        )
        main = line_image(lines.main, main_size, font_path, style)
    tag = None
    if lines.top:
        tag_size = fit_size(
            lines.top,
            font_path,
            style,
            round(width * style.top_width),
            round(height * style.top_cap),
        )
        tag = line_image(lines.top, tag_size, font_path, style)

    stack = [image for image in (tag, main) if image is not None]
    if not stack:
        return []
    needed = sum(image.height for image in stack) + gap * (len(stack) - 1) + art_gap
    if needed > room:
        scale = (room - art_gap) / max(1, needed - art_gap)
        stack = [
            image.resize(
                (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                Image.LANCZOS,
            )
            for image in stack
        ]
        if tag is not None:
            tag = stack[0]
        main = stack[-1]

    result: list[_Placed] = []
    y = bottom_limit - art_gap
    main_x = round(width * style.side_margin)
    if main is not None:
        main_x = (width - main.width) // 2
        y -= main.height
        result.append(_Placed(main, main_x, y))
    if tag is not None:
        y -= gap + tag.height
        # Hang the tag just off the big line's left edge rather than parking it
        # in the corner, so the two read as one block however wide the big line.
        x = max(round(width * 0.035), main_x - round(tag.height * 0.55))
        result.append(_Placed(tag, x, max(0, y)))
    return result


def _place_bottom_line(
    lines: TitleLines,
    font_path: str,
    style: TitleStyle,
    size: tuple[int, int],
    band: tuple[int, int],
) -> list[_Placed]:
    width, height = size
    top_limit, bottom_limit = band
    art_gap = round(height * style.art_gap)
    room = bottom_limit - top_limit - art_gap
    if not lines.bottom or room <= 0:
        return []

    line_size = fit_size(
        lines.bottom,
        font_path,
        style,
        round(width * style.bottom_width),
        min(round(height * style.bottom_cap), room),
    )
    ink = line_image(lines.bottom, line_size, font_path, style)
    y = top_limit + art_gap
    # Sit in the middle of the free band when there is room to spare.
    y += max(0, (room - ink.height) // 2)
    return [_Placed(ink, (width - ink.width) // 2, y)]


def add_title(
    image: Image.Image,
    title: str | TitleLines,
    style: TitleStyle | None = None,
    font: str | None = None,
    band: tuple[int, int] | None = None,
) -> tuple[Image.Image, TitleLines, tuple[int, int]]:
    """Draw ``title`` on ``image``, above and below the card artwork."""
    style = style or TitleStyle()
    lines = split_title(title) if isinstance(title, str) else title
    if not lines:
        raise ValueError("nothing to draw: the title is empty")

    font_path = find_font(font)
    art = band or find_artwork_band(image)
    out = image.convert("RGB").copy()
    size = out.size

    placements = _place_top_lines(lines, font_path, style, size, (0, art[0]))
    placements += _place_bottom_line(lines, font_path, style, size, (art[1], size[1]))
    for item in placements:
        out.paste(item.image, (item.x, item.y), item.image)
    return out, lines, art
