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


def match_tile(
    crop: np.ndarray, templates: dict[str, np.ndarray], threshold: float = 0.55
) -> tuple[str | None, float]:
    """Best-matching template label for a single tile crop, or (None, score)."""
    if not templates:
        return None, 0.0
    probe = _prep(crop)
    best_label, best_score = None, -1.0
    for label, template in templates.items():
        score = float(cv2.matchTemplate(probe, template, cv2.TM_CCOEFF_NORMED)[0, 0])
        if score > best_score:
            best_label, best_score = label, score
    if best_score < threshold:
        return None, best_score
    return best_label, best_score


def recognize_hand(
    image: np.ndarray, tile_count: int, templates: dict[str, np.ndarray], threshold: float = 0.55
) -> tuple[list[str | None], list[int]]:
    """Recognize every slot in a hand row. Returns (labels, unmatched slot indices)."""
    from mahjong_advisor.vision.capture import slice_into_tiles

    labels: list[str | None] = []
    unmatched: list[int] = []
    for i, crop in enumerate(slice_into_tiles(image, tile_count)):
        label, _score = match_tile(crop, templates, threshold)
        labels.append(label)
        if label is None:
            unmatched.append(i)
    return labels, unmatched


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
