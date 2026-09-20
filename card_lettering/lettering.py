"""Draw a line of heavy white text inside a thick coloured outline.

Both the listing-title tool and the stat-stamp tool letter their text this way,
so the font hunt, the synthetic weight and the character spacing live here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


@dataclass
class LetterStyle:
    """Colours and proportions of the lettering. Sizes scale with the font size."""

    fill: tuple[int, int, int] = (255, 255, 255)
    outline: tuple[int, int, int] = (228, 30, 38)
    # Stroke added to every glyph, as a fraction of the font size: this is what
    # turns a regular gothic into a heavy one. Past about 0.04 the counters of
    # dense kanji fill in, so a genuinely heavy font wants a lower value here.
    weight_ratio: float = 0.035
    # Outline thickness, as a fraction of the font size.
    outline_ratio: float = 0.145
    # Gap between the INK of neighbouring characters, as a fraction of the font
    # size. Spacing by ink rather than by advance keeps katakana, which sits
    # well inside its em box, from drifting apart from the kanji next to it.
    tracking_ratio: float = 0.05
    # How much of the blank margin a font leaves on each side of a character to
    # keep. 0 spaces purely by ink, 1 is the font's own advance width; narrow
    # katakana need some of it back or they read tighter than the kanji.
    bearing_ratio: float = 0.45
    # Gap where the text had a space, as a fraction of the font size.
    word_gap_ratio: float = 0.34


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


def _draw_line(
    text: str,
    font: ImageFont.FreeTypeFont,
    weight: int,
    outline: int,
    tracking: int,
    word_gap: int,
    bearing: float,
    style: LetterStyle,
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


def line_image(text: str, size: int, font_path: str, style: LetterStyle) -> Image.Image:
    """Render one line at ``size``, cropped to its ink."""
    font = ImageFont.truetype(font_path, size)
    weight = round(size * style.weight_ratio)
    outline = round(size * style.outline_ratio)
    tracking = round(size * style.tracking_ratio)
    word_gap = round(size * style.word_gap_ratio)
    return _draw_line(
        text, font, weight, outline, tracking, word_gap, style.bearing_ratio, style
    )


def fit_size(
    text: str, font_path: str, style: LetterStyle, max_width: int, max_height: int
) -> int:
    """Largest font size whose ink fits inside the given box."""
    low, high = 8, max(12, max_height * 3)
    best = low
    while low <= high:
        mid = (low + high) // 2
        ink = line_image(text, mid, font_path, style)
        if ink.width <= max_width and ink.height <= max_height:
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    return best
