"""Highlight one grade chip in a PSA population screenshot.

Blacks out every grade chip except the target one and draws a large arrow
pointing at it, so a single grade can be shown without the surrounding noise.
"""

from .marker import (
    Chip,
    ChipRow,
    MarkerStyle,
    detect_chip_row,
    highlight_grade,
    render_highlight,
)

__all__ = [
    "Chip",
    "ChipRow",
    "MarkerStyle",
    "detect_chip_row",
    "highlight_grade",
    "render_highlight",
]
