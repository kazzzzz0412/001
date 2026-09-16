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


def slice_into_grid(image: np.ndarray, columns: int, rows: int) -> list[np.ndarray]:
    """Split a discard pile into cells, reading left-to-right then top-to-bottom
    - the order tiles are actually discarded in."""
    if columns <= 0 or rows <= 0:
        raise ValueError("columns and rows must be positive")
    height, width = image.shape[:2]
    cell_width = width // columns
    cell_height = height // rows
    if cell_width == 0 or cell_height == 0:
        raise ValueError("capture region is too small for the requested grid")

    cells = []
    for row in range(rows):
        y0 = row * cell_height
        y1 = height if row == rows - 1 else (row + 1) * cell_height
        for column in range(columns):
            x0 = column * cell_width
            x1 = width if column == columns - 1 else (column + 1) * cell_width
            cells.append(image[y0:y1, x0:x1])
    return cells
