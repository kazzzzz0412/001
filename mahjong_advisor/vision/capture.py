"""Screen capture and hand-row slicing helpers (experimental vision mode)."""

from __future__ import annotations

import numpy as np


def grab_region(region: dict) -> np.ndarray:
    """Capture a screen region (mss-style dict) and return it as a BGR array."""
    import mss

    with mss.mss() as sct:
        raw = sct.grab(region)
        img = np.array(raw)  # BGRA
    return img[:, :, :3]


def slice_into_tiles(image: np.ndarray, tile_count: int) -> list[np.ndarray]:
    """Split a hand-row image into `tile_count` equal-width vertical slots.

    Assumes the calibrated region tightly bounds an evenly-spaced hand row,
    which holds for most clients but not all - recalibrate tile_count to
    match what's actually on screen (13 before your draw, 14 after).
    """
    if tile_count <= 0:
        raise ValueError("tile_count must be positive")
    height, width = image.shape[:2]
    slot_width = width // tile_count
    if slot_width == 0:
        raise ValueError("capture region is too narrow for the requested tile_count")

    slots = []
    for i in range(tile_count):
        x0 = i * slot_width
        x1 = width if i == tile_count - 1 else (i + 1) * slot_width
        slots.append(image[:, x0:x1])
    return slots
