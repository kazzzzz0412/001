import numpy as np
import cv2
import pytest

from mahjong_advisor.vision.capture import slice_into_tiles
from mahjong_advisor.vision.recognizer import (
    labels_to_hand_string,
    load_templates,
    match_tile,
    recognize_hand,
)


def _render_tile(text: str, size=(48, 72)) -> np.ndarray:
    """Draw a synthetic, visually distinct tile image for a given label."""
    width, height = size
    img = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.putText(img, text, (2, height // 2 + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    return img


def _make_templates_dir(tmp_path, labels):
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    for label in labels:
        cv2.imwrite(str(templates_dir / f"{label}.png"), _render_tile(label))
    return templates_dir


def test_slice_into_tiles_splits_evenly():
    image = np.zeros((60, 140, 3), dtype=np.uint8)
    slots = slice_into_tiles(image, 14)
    assert len(slots) == 14
    # last slot absorbs the remainder, others share the width evenly
    widths = [s.shape[1] for s in slots]
    assert widths[:-1] == [140 // 14] * 13
    assert sum(widths) == 140


def test_slice_into_tiles_rejects_too_narrow_region():
    image = np.zeros((60, 5, 3), dtype=np.uint8)
    with pytest.raises(ValueError):
        slice_into_tiles(image, 14)


def test_load_templates_and_match_exact(tmp_path):
    labels = ["5m", "1z", "9s"]
    templates_dir = _make_templates_dir(tmp_path, labels)
    templates = load_templates(templates_dir)
    assert set(templates) == set(labels)

    for label in labels:
        crop = _render_tile(label)
        best_label, score = match_tile(crop, templates, threshold=0.5)
        assert best_label == label
        assert score > 0.9


def test_match_tile_below_threshold_returns_none(tmp_path):
    templates_dir = _make_templates_dir(tmp_path, ["5m"])
    templates = load_templates(templates_dir)
    noise = np.random.randint(0, 255, (72, 48, 3), dtype=np.uint8)
    label, score = match_tile(noise, templates, threshold=0.9)
    assert label is None


def test_recognize_hand_end_to_end(tmp_path):
    labels = ["1m", "2m", "3m", "5p", "1z"]
    templates_dir = _make_templates_dir(tmp_path, labels)
    templates = load_templates(templates_dir)

    tile_w, tile_h = 48, 72
    row = np.concatenate([_render_tile(l, (tile_w, tile_h)) for l in labels], axis=1)

    recognized, unmatched = recognize_hand(row, len(labels), templates, threshold=0.5)
    assert unmatched == []
    assert recognized == labels
    assert labels_to_hand_string(recognized) == "123m5p1z"


def test_recognize_hand_reports_unmatched_slots(tmp_path):
    templates_dir = _make_templates_dir(tmp_path, ["1m"])
    templates = load_templates(templates_dir)

    tile_w, tile_h = 48, 72
    row = np.concatenate([_render_tile("1m", (tile_w, tile_h)), _render_tile("9s", (tile_w, tile_h))], axis=1)

    recognized, unmatched = recognize_hand(row, 2, templates, threshold=0.9)
    assert unmatched == [1]
    assert recognized[0] == "1m"
    assert recognized[1] is None


def test_labels_to_hand_string_groups_and_sorts():
    assert labels_to_hand_string(["3m", "1m", "2m"]) == "123m"
    assert labels_to_hand_string(["5p", "9m", "1z", "1m"]) == "19m5p1z"
    assert labels_to_hand_string([]) == ""
