"""Lay a listing title over a photo of cards without covering the artwork.

The caption style is the one marketplace listings use: heavy white gothic
Japanese text inside a thick red outline. Text goes in the empty bands above
and below the cards, so the artwork itself stays visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Fonts to try, most preferred first. A weight heavier than regular is better,
# but a regular gothic is thickened below, so either works.
FONT_CANDIDATES: tuple[str, ...] = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Bold.otf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipagp.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "C:/Windows/Fonts/meiryob.ttc",
    "C:/Windows/Fonts/YuGothB.ttc",
)

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
class TitleStyle:
    """Colours and proportions of the caption. Sizes scale with the photo."""

    fill: tuple[int, int, int] = (255, 255, 255)
    outline: tuple[int, int, int] = (228, 30, 38)
    # Stroke added to every glyph, as a fraction of the font size: this is what
    # turns a regular gothic into a heavy one. Past about 0.04 the counters of
    # dense kanji fill in, so a genuinely heavy font wants a lower value here.
    weight_ratio: float = 0.035
    # Red outline thickness, as a fraction of the font size.
    outline_ratio: float = 0.145
    # Gap between the INK of neighbouring characters, as a fraction of the font
    # size. Spacing by ink rather than by advance keeps katakana, which sits
    # well inside its em box, from drifting apart from the kanji next to it.
    tracking_ratio: float = 0.05
    # How much of the blank margin a font leaves on each side of a character to
    # keep. 0 spaces purely by ink, 1 is the font's own advance width; narrow
    # katakana need some of it back or they read tighter than the kanji.
    bearing_ratio: float = 0.45
    # Gap where the title had a space, as a fraction of the font size.
    word_gap_ratio: float = 0.34
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


def find_font(preferred: str | None = None) -> str:
    """Path of the first usable gothic font."""
    candidates = (preferred,) + FONT_CANDIDATES if preferred else FONT_CANDIDATES
    for path in candidates:
        if path and Path(path).exists():
            try:
                ImageFont.truetype(path, 24)
            except OSError:
                continue
            return path
    raise FileNotFoundError(
        "no Japanese gothic font found; pass one with --font "
        "(e.g. a Noto Sans CJK or IPAGothic .ttf/.otf)"
    )


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


def _ink(
    text: str,
    font: ImageFont.FreeTypeFont,
    weight: int,
    outline: int,
    tracking: int,
    word_gap: int,
    bearing: float,
    style: TitleStyle,
) -> Image.Image:
    """One line of text, cropped to its own ink.

    Characters are placed one at a time, a fixed gap apart plus a share of the
    blank margins the font gives them: set solid they would run together at this
    outline thickness, while keeping those margins whole - which is what spacing
    by advance width does - strings the narrow katakana out. The outlines are
    all drawn first, then the fills, so no outline crosses the letter before it.
    """
    placements: list[tuple[str, float]] = []
    cursor = 0.0
    trailing = 0.0  # right side bearing of the character just placed
    for character in text:
        if character.isspace():
            cursor += word_gap - tracking
            trailing = 0.0
            continue
        # getbbox reports the layout box, so the ink itself is measured from a
        # rendered mask: that is what the gap is counted from.
        ink = font.getmask(character, mode="L").getbbox()
        if ink is None:  # a glyph with no ink of its own
            cursor += font.getlength(character) + tracking
            trailing = 0.0
            continue
        left, right = ink[0], ink[2]
        if placements:
            cursor += bearing * (trailing + left)
        draw_x = cursor - left
        placements.append((character, draw_x))
        cursor = draw_x + right + tracking
        trailing = font.getlength(character) - right
    line_width = max(0.0, cursor - tracking)

    ascent, descent = font.getmetrics()
    pad = weight + outline + 8
    layer = Image.new(
        "RGBA",
        (round(line_width) + 2 * pad, ascent + descent + 2 * pad),
        (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(layer)
    for color, stroke in (
        (style.outline, weight + outline),
        (style.fill, weight),
    ):
        for character, offset in placements:
            draw.text(
                (pad + offset, pad),
                character,
                font=font,
                fill=color,
                stroke_width=stroke,
                stroke_fill=color,
            )
    box = layer.getbbox()
    return layer.crop(box) if box else layer


def _line_image(
    text: str, size: int, font_path: str, style: TitleStyle
) -> Image.Image:
    font = ImageFont.truetype(font_path, size)
    weight = round(size * style.weight_ratio)
    outline = round(size * style.outline_ratio)
    tracking = round(size * style.tracking_ratio)
    word_gap = round(size * style.word_gap_ratio)
    return _ink(text, font, weight, outline, tracking, word_gap, style.bearing_ratio, style)


def _fit_size(
    text: str, font_path: str, style: TitleStyle, max_width: int, max_height: int
) -> int:
    """Largest font size whose ink fits inside the given box."""
    low, high = 8, max(12, max_height * 3)
    best = low
    while low <= high:
        mid = (low + high) // 2
        ink = _line_image(text, mid, font_path, style)
        if ink.width <= max_width and ink.height <= max_height:
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    return best


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
        main_size = _fit_size(
            lines.main,
            font_path,
            style,
            round(width * style.main_width),
            round(height * style.main_cap),
        )
        main = _line_image(lines.main, main_size, font_path, style)
    tag = None
    if lines.top:
        tag_size = _fit_size(
            lines.top,
            font_path,
            style,
            round(width * style.top_width),
            round(height * style.top_cap),
        )
        tag = _line_image(lines.top, tag_size, font_path, style)

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

    line_size = _fit_size(
        lines.bottom,
        font_path,
        style,
        round(width * style.bottom_width),
        min(round(height * style.bottom_cap), room),
    )
    ink = _line_image(lines.bottom, line_size, font_path, style)
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
