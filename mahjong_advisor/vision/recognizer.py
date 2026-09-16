"""Template-matching tile recognition (experimental vision mode).

Requires per-client calibration: run `python main.py calibrate` first to
build a folder of labeled tile crops (`templates/5m.png`, `templates/1z.png`,
...) captured from your actual game client. There is no universal template
set because every online mahjong client uses a different tile skin.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

CANONICAL_SIZE = (48, 72)  # (width, height) every crop/template is normalized to

EMPTY_LABEL = "_empty"
"""Template name for bare table felt. Calibrating one lets the recognizer tell
an empty slot in a discard pile from a tile, instead of guessing a tile."""


def _prep(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return cv2.resize(gray, CANONICAL_SIZE, interpolation=cv2.INTER_AREA)


def load_templates(templates_dir: str | Path) -> dict[str, np.ndarray]:
    templates: dict[str, np.ndarray] = {}
    directory = Path(templates_dir)
    if not directory.exists():
        return templates
    for path in sorted(directory.glob("*.png")):
        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if img is None:
            continue
        templates[path.stem] = _prep(img)
    return templates


_FLAT_IMAGE_STD = 1e-3


def similarity(probe: np.ndarray, template: np.ndarray) -> float:
    """How well two normalized crops match, as 0.0-1.0.

    Normalized cross-correlation is undefined when either image has no
    variance, and bare table felt is very nearly flat - so an `_empty`
    template would otherwise produce NaN scores and match at random. Compare
    those by pixel distance instead.
    """
    if probe.std() < _FLAT_IMAGE_STD or template.std() < _FLAT_IMAGE_STD:
        distance = np.abs(probe.astype(np.float32) - template.astype(np.float32)).mean()
        return max(0.0, 1.0 - distance / 255.0)

    score = float(cv2.matchTemplate(probe, template, cv2.TM_CCOEFF_NORMED)[0, 0])
    return score if np.isfinite(score) else 0.0


def match_tile(
    crop: np.ndarray, templates: dict[str, np.ndarray], threshold: float = 0.55
) -> tuple[str | None, float]:
    """Best-matching template label for a single tile crop, or (None, score)."""
    if not templates:
        return None, 0.0
    probe = _prep(crop)
    best_label, best_score = None, -1.0
    for label, template in templates.items():
        score = similarity(probe, template)
        if score > best_score:
            best_label, best_score = label, score
    if best_score < threshold:
        return None, best_score
    return best_label, best_score


def recognize_hand(
    image: np.ndarray, tile_count: int, templates: dict[str, np.ndarray], threshold: float = 0.55
) -> tuple[list[str | None], list[int]]:
    """Recognize every slot in a hand row. Returns (labels, unmatched slot indices).

    Empty slots are dropped rather than reported, so a region sized for 14 tiles
    still reads correctly on the 13 tiles you hold before drawing.
    """
    from mahjong_advisor.vision.capture import slice_into_tiles

    labels: list[str | None] = []
    unmatched: list[int] = []
    for i, crop in enumerate(slice_into_tiles(image, tile_count)):
        label, _score = match_tile(crop, templates, threshold)
        if label == EMPTY_LABEL:
            continue
        labels.append(label)
        if label is None:
            unmatched.append(i)
    return labels, unmatched


def recognize_pile(
    image: np.ndarray,
    columns: int,
    rows: int,
    templates: dict[str, np.ndarray],
    threshold: float = 0.55,
) -> tuple[list[str], list[int]]:
    """Read a discard pile in discard order.

    Tiles fill the grid in order, so reading stops at the first empty cell -
    anything after it is empty too. Returns (labels, unreadable cell indices);
    an unreadable cell before the end of the pile is usually the sideways
    riichi declaration tile, which upright templates cannot match.
    """
    from mahjong_advisor.vision.capture import slice_into_grid

    labels: list[str] = []
    unreadable: list[int] = []

    for index, cell in enumerate(slice_into_grid(image, columns, rows)):
        label, _score = match_tile(cell, templates, threshold)
        if label == EMPTY_LABEL:
            break
        if label is None:
            unreadable.append(index)
            continue
        labels.append(label)

    return labels, unreadable


def labels_to_tiles(labels: list[str]) -> list[int]:
    """['5m','1z'] -> [34-index, ...], preserving order."""
    suit_base = {"m": 0, "p": 9, "s": 18, "z": 27}
    tiles = []
    for label in labels:
        rank, suit = label[:-1], label[-1]
        if suit not in suit_base or not rank.isdigit():
            raise ValueError(f"unrecognized tile label: {label!r}")
        value = int(rank)
        if suit == "z":
            if not 1 <= value <= 7:
                raise ValueError(f"unrecognized tile label: {label!r}")
        else:
            if value == 0:
                value = 5  # red five
            if not 1 <= value <= 9:
                raise ValueError(f"unrecognized tile label: {label!r}")
        tiles.append(suit_base[suit] + value - 1)
    return tiles


def labels_to_hand_string(labels: list[str]) -> str:
    """['5m','1z','3m'] -> '35m1z' (mpsz notation, grouped and sorted per suit)."""
    groups = {suit: [] for suit in "mpsz"}
    for label in labels:
        if not label:
            continue
        rank, suit = label[:-1], label[-1]
        if suit not in groups:
            raise ValueError(f"unrecognized tile label: {label!r}")
        groups[suit].append(rank)

    parts = []
    for suit in "mpsz":
        ranks = sorted(groups[suit], key=int)
        if ranks:
            parts.append("".join(ranks) + suit)
    return "".join(parts)
