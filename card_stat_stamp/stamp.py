"""Stamp the grade, the population count and today's date onto a slab photo.

Three lines in the same heavy white-on-red lettering the title tool uses: the
grade and the population over the middle of the card, and the date it was read
down near the bottom. Unlike the title tool this one is meant to sit on top of
the card - the numbers are the point - so it is placed by proportion rather
than by hunting for free space.

Where the numbers come from: the grade is on the slab's own label (the number
beside GEM MT / NM-MT at the top right), and the population is the count on the
grading-distribution screen for that same grade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from PIL import Image

from card_lettering import LetterStyle, find_font, fit_size, line_image


@dataclass(frozen=True)
class StampText:
    """The three lines, already worded."""

    grade: str = ""
    pop: str = ""
    date: str = ""

    def __bool__(self) -> bool:
        return bool(self.grade or self.pop or self.date)


@dataclass
class StampStyle(LetterStyle):
    """Where the three lines sit, as fractions of the photo."""

    # Latin capitals and digits keep their counters open at a weight that would
    # clog a kanji, so when the font has to be thickened it can take more.
    synthetic_weight: float = 0.055
    # Ink height of each line.
    grade_cap: float = 0.0585
    pop_cap: float = 0.0715
    date_cap: float = 0.041
    # Widest any line may be.
    line_width: float = 0.80
    # Top of the grade line, and the gap to the population line under it.
    block_top: float = 0.600
    line_gap: float = 0.008
    # Top of the date line, and its distance from the right edge.
    date_top: float = 0.880
    date_margin: float = 0.107


def format_stamp(
    grade: str | int | None = None,
    pop: str | int | None = None,
    when: date | str | None = None,
) -> StampText:
    """Word the three lines: ``PSA10``, ``POP 176``, ``2026/09/20 時点``."""
    grade_text = ""
    if grade is not None and str(grade).strip():
        digits = str(grade).strip().upper().removeprefix("PSA").strip()
        grade_text = f"PSA{digits}"

    pop_text = ""
    if pop is not None and str(pop).strip():
        pop_text = f"POP {str(pop).strip()}"

    date_text = ""
    if when is not None:
        stamped = when if isinstance(when, str) else when.strftime("%Y/%m/%d")
        date_text = f"{stamped.replace('-', '/')} 時点"

    return StampText(grade=grade_text, pop=pop_text, date=date_text)


def _place(
    text: str,
    cap: float,
    font_path: str,
    style: StampStyle,
    size: tuple[int, int],
) -> Image.Image | None:
    if not text:
        return None
    width, height = size
    point = fit_size(
        text, font_path, style, round(width * style.line_width), round(height * cap)
    )
    return line_image(text, point, font_path, style)


def add_stamp(
    image: Image.Image,
    text: StampText,
    style: StampStyle | None = None,
    font: str | None = None,
) -> Image.Image:
    """Draw ``text`` over ``image`` and return the result."""
    if not text:
        raise ValueError("nothing to stamp: no grade, population or date given")

    style = style or StampStyle()
    font_path = find_font(font)
    out = image.convert("RGB").copy()
    width, height = out.size

    grade = _place(text.grade, style.grade_cap, font_path, style, out.size)
    pop = _place(text.pop, style.pop_cap, font_path, style, out.size)
    stamped = _place(text.date, style.date_cap, font_path, style, out.size)

    y = round(height * style.block_top)
    for line in (grade, pop):
        if line is None:
            continue
        out.paste(line, ((width - line.width) // 2, y), line)
        y += line.height + round(height * style.line_gap)

    if stamped is not None:
        x = width - round(width * style.date_margin) - stamped.width
        out.paste(stamped, (max(0, x), round(height * style.date_top)), stamped)
    return out
