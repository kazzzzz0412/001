"""Burn a listing title onto a photo of cards, clear of the card artwork.

Draws bold white Japanese text with a thick red outline, the way a marketplace
listing thumbnail is usually captioned, and keeps it in the empty bands above
and below the cards.
"""

from .overlay import (
    TitleLines,
    TitleStyle,
    add_title,
    find_artwork_band,
    find_font,
    split_title,
)

__all__ = [
    "TitleLines",
    "TitleStyle",
    "add_title",
    "find_artwork_band",
    "find_font",
    "split_title",
]
