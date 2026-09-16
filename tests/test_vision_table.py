import cv2
import numpy as np
import pytest
from mahjong.tile import TilesConverter

from mahjong_advisor.config import CaptureRegion, GridRegion, VisionConfig
from mahjong_advisor.engine.table import TableState
from mahjong_advisor.session import AdvisorSession
from mahjong_advisor.vision.capture import slice_into_grid
from mahjong_advisor.vision.recognizer import (
    EMPTY_LABEL,
    labels_to_tiles,
    load_templates,
    match_tile,
    recognize_hand,
    recognize_pile,
    similarity,
)
from mahjong_advisor.vision.sync import diff_pile, sync_pile


def idx(notation: str) -> int:
    return TilesConverter.one_line_string_to_34_array(notation).index(1)


def _render_tile(text: str, size=(48, 72)) -> np.ndarray:
    width, height = size
    img = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.putText(img, text, (2, height // 2 + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    return img


def _render_empty(size=(48, 72)) -> np.ndarray:
    """Plain table felt - no tile."""
    width, height = size
    return np.full((height, width, 3), (60, 110, 70), dtype=np.uint8)


def _templates_dir(tmp_path, labels, with_empty=True):
    directory = tmp_path / "templates"
    directory.mkdir(exist_ok=True)
    for label in labels:
        cv2.imwrite(str(directory / f"{label}.png"), _render_tile(label))
    if with_empty:
        cv2.imwrite(str(directory / f"{EMPTY_LABEL}.png"), _render_empty())
    return directory


def _render_pile(labels, columns=6, rows=3, size=(48, 72)):
    """Lay tiles into a grid left-to-right, top-to-bottom; pad with felt."""
    cells = [_render_tile(label, size) for label in labels]
    cells += [_render_empty(size) for _ in range(columns * rows - len(cells))]
    grid_rows = [
        np.concatenate(cells[row * columns : (row + 1) * columns], axis=1) for row in range(rows)
    ]
    return np.concatenate(grid_rows, axis=0)


# --- grid slicing -----------------------------------------------------------
def test_slice_into_grid_reads_in_discard_order():
    cells = []
    for row in range(3):
        for column in range(6):
            cells.append(np.full((10, 10, 3), row * 6 + column, dtype=np.uint8))
    grid_rows = [np.concatenate(cells[r * 6 : (r + 1) * 6], axis=1) for r in range(3)]
    image = np.concatenate(grid_rows, axis=0)

    sliced = slice_into_grid(image, columns=6, rows=3)
    assert len(sliced) == 18
    # cell N should carry value N, i.e. left-to-right then top-to-bottom
    assert [int(cell[0, 0, 0]) for cell in sliced] == list(range(18))


def test_slice_into_grid_rejects_a_region_too_small():
    with pytest.raises(ValueError):
        slice_into_grid(np.zeros((5, 5, 3), dtype=np.uint8), columns=6, rows=3)


# --- matching against a flat template ---------------------------------------
def test_similarity_handles_a_flat_template():
    """Bare felt has no variance, which makes normalized cross-correlation
    undefined - the score must still be finite and meaningful."""
    felt = np.full((72, 48), 95, dtype=np.uint8)
    identical = np.full((72, 48), 95, dtype=np.uint8)
    tile = np.full((72, 48), 250, dtype=np.uint8)

    assert np.isfinite(similarity(felt, identical))
    assert similarity(felt, identical) > 0.95
    assert similarity(tile, felt) < similarity(felt, identical)


def test_empty_cell_is_not_mistaken_for_a_tile(tmp_path):
    templates = load_templates(_templates_dir(tmp_path, ["1m", "9p"]))
    label, _score = match_tile(_render_empty(), templates, threshold=0.5)
    assert label == EMPTY_LABEL


def test_tile_is_not_mistaken_for_an_empty_cell(tmp_path):
    templates = load_templates(_templates_dir(tmp_path, ["1m", "9p"]))
    label, _score = match_tile(_render_tile("9p"), templates, threshold=0.5)
    assert label == "9p"


# --- pile recognition -------------------------------------------------------
def test_recognize_pile_stops_at_the_first_empty_cell(tmp_path):
    labels = ["1m", "9p", "5s"]
    templates = load_templates(_templates_dir(tmp_path, labels))
    image = _render_pile(labels)

    read, unreadable = recognize_pile(image, 6, 3, templates, threshold=0.5)
    assert read == labels
    assert unreadable == []


def test_recognize_pile_of_a_full_row_continues_to_the_next(tmp_path):
    labels = ["1m", "2m", "3m", "4m", "5m", "6m", "7m", "8m"]
    templates = load_templates(_templates_dir(tmp_path, labels))
    image = _render_pile(labels)

    read, _ = recognize_pile(image, 6, 3, templates, threshold=0.5)
    assert read == labels  # wraps from row 1 into row 2


def test_recognize_pile_reports_an_unreadable_cell(tmp_path):
    """The sideways riichi tile won't match any upright template."""
    templates = load_templates(_templates_dir(tmp_path, ["1m", "9p"]))
    image = _render_pile(["1m", "5z", "9p"])  # 5z has no template

    read, unreadable = recognize_pile(image, 6, 3, templates, threshold=0.9)
    assert unreadable == [1]
    assert read == ["1m", "9p"]


def test_empty_pile_reads_as_nothing(tmp_path):
    templates = load_templates(_templates_dir(tmp_path, ["1m"]))
    read, unreadable = recognize_pile(_render_pile([]), 6, 3, templates, threshold=0.5)
    assert read == []
    assert unreadable == []


def test_hand_region_sized_for_14_reads_13_tiles(tmp_path):
    """Before your draw the last slot is empty - that's not an error."""
    labels = [f"{n}m" for n in range(1, 10)] + ["1p", "2p", "3p", "4p"]
    templates = load_templates(_templates_dir(tmp_path, labels))
    cells = [_render_tile(label) for label in labels] + [_render_empty()]
    image = np.concatenate(cells, axis=1)

    read, unmatched = recognize_hand(image, 14, templates, threshold=0.5)
    assert unmatched == []
    assert read == labels


def test_labels_to_tiles_preserves_order():
    assert labels_to_tiles(["9p", "1m", "1z"]) == [idx("9p"), idx("1m"), idx("1z")]


def test_labels_to_tiles_maps_red_five():
    assert labels_to_tiles(["0p"]) == [idx("5p")]


def test_labels_to_tiles_rejects_garbage():
    with pytest.raises(ValueError):
        labels_to_tiles(["xx"])


# --- incremental sync -------------------------------------------------------
def test_diff_pile_returns_only_the_new_tail():
    known = [1, 2, 3]
    assert diff_pile(known, [1, 2, 3, 4, 5]) == [4, 5]


def test_diff_pile_on_an_unchanged_pile_returns_nothing():
    assert diff_pile([1, 2, 3], [1, 2, 3]) == []


def test_diff_pile_survives_a_called_tile_disappearing():
    """Pon/chi removes a tile from the middle of the pile - everything after it
    must not look new."""
    known = [1, 2, 3, 4]
    observed = [1, 3, 4, 7]  # 2 was called away, 7 is genuinely new
    assert diff_pile(known, observed) == [7]


def test_diff_pile_handles_duplicate_tiles():
    known = [5, 5]
    assert diff_pile(known, [5, 5, 5]) == [5]


def test_sync_pile_appends_to_the_table_state():
    table = TableState()
    table.discard(2, idx("1m"))

    result = sync_pile(table, 2, [idx("1m"), idx("9p")])
    assert result.added == [idx("9p")]
    assert table.opponents[1].discards == [idx("1m"), idx("9p")]


def test_sync_pile_keeps_called_tiles_in_history():
    """A tile that left the pile was still discarded, so it stays genbutsu."""
    table = TableState()
    for tile in ("1m", "9p"):
        table.discard(2, idx(tile))

    sync_pile(table, 2, [idx("9p")])  # 1m was called away and is gone from screen
    assert idx("1m") in table.opponents[2 - 1].discards
    assert idx("1m") in table.safe_tiles(table.opponents[1])


def test_sync_pile_rejects_an_implausible_read():
    table = TableState()
    bogus = [idx("1m")] * 10

    result = sync_pile(table, 1, bogus)
    assert result.suspicious
    assert result.added == []
    assert table.opponents[0].discards == []


def test_sync_pile_feeds_the_danger_model():
    """The whole point: a screen read should make tiles show up as genbutsu."""
    session = AdvisorSession()
    session.handle("t 9")
    session.handle("r2")
    sync_pile(session.table, 2, [idx("1z"), idx("9p"), idx("2m"), idx("5m")])

    output = session.handle("2345699m44p567s11z")
    assert "現物" in output


def test_sync_pile_rejects_a_bad_player_index():
    with pytest.raises(ValueError):
        sync_pile(TableState(), 5, [])


# --- config round trip ------------------------------------------------------
def test_config_round_trips_discard_regions(tmp_path):
    path = tmp_path / "config.json"
    config = VisionConfig(
        hand_region=CaptureRegion(left=1, top=2, width=300, height=50),
        discard_regions={2: GridRegion(left=10, top=20, width=180, height=210, columns=6, rows=3)},
    )
    config.save(path)

    loaded = VisionConfig.load(path)
    assert set(loaded.discard_regions) == {2}  # int key, not the JSON string
    grid = loaded.discard_regions[2]
    assert (grid.columns, grid.rows) == (6, 3)
    assert grid.as_mss_region() == {"left": 10, "top": 20, "width": 180, "height": 210}


def test_config_without_discard_regions_loads_empty(tmp_path):
    path = tmp_path / "config.json"
    VisionConfig(hand_region=CaptureRegion(0, 0, 10, 10)).save(path)
    assert VisionConfig.load(path).discard_regions == {}


# --- end to end: fake screen -> advice ---------------------------------------
HAND_LABELS = [
    "2m", "3m", "4m", "5m", "6m", "9m", "9m", "4p", "4p", "5s", "6s", "7s", "1z", "1z",
]
PILE_LABELS = ["1z", "9p", "2m", "5m"]


def _fake_screen(monkeypatch, hand_labels, pile_labels):
    """Serve synthetic captures in place of real screen grabs."""
    hand_image = np.concatenate([_render_tile(label) for label in hand_labels], axis=1)
    pile_image = _render_pile(pile_labels)

    def fake_grab(region):
        # The hand region is the wide, short one; the pile is the tall grid.
        return hand_image if region["height"] == 72 else pile_image

    monkeypatch.setattr("mahjong_advisor.vision.runner.grab_region", fake_grab)


def _vision_config(tmp_path, labels):
    return VisionConfig(
        hand_region=CaptureRegion(left=0, top=0, width=48 * 14, height=72),
        tile_count=len(HAND_LABELS),
        discard_regions={2: GridRegion(left=0, top=0, width=48 * 6, height=72 * 3)},
        templates_dir=str(_templates_dir(tmp_path, labels)),
        match_threshold=0.5,
    )


def test_read_table_recognizes_hand_and_pile_and_advises(tmp_path, monkeypatch):
    from mahjong_advisor.vision.runner import read_table

    config = _vision_config(tmp_path, set(HAND_LABELS) | set(PILE_LABELS))
    _fake_screen(monkeypatch, HAND_LABELS, PILE_LABELS)

    session = AdvisorSession()
    session.handle("t 9")
    session.handle("r2")  # 対面 riichi, so danger reading turns on

    output = read_table(session, config)

    # the pile was read into the table state
    assert session.table.opponents[1].discards == labels_to_tiles(PILE_LABELS)
    # and it fed the advice
    assert "認識した手牌" in output
    assert "切るなら" in output
    assert "現物" in output


def test_read_table_twice_does_not_double_count_the_pile(tmp_path, monkeypatch):
    """Re-reading an unchanged screen must not append the pile again."""
    from mahjong_advisor.vision.runner import read_table

    config = _vision_config(tmp_path, set(HAND_LABELS) | set(PILE_LABELS))
    _fake_screen(monkeypatch, HAND_LABELS, PILE_LABELS)

    session = AdvisorSession()
    read_table(session, config)
    read_table(session, config)

    assert session.table.opponents[1].discards == labels_to_tiles(PILE_LABELS)


def test_read_table_picks_up_only_newly_discarded_tiles(tmp_path, monkeypatch):
    from mahjong_advisor.vision.runner import read_table

    labels = set(HAND_LABELS) | set(PILE_LABELS) | {"3s"}
    config = _vision_config(tmp_path, labels)

    session = AdvisorSession()
    _fake_screen(monkeypatch, HAND_LABELS, PILE_LABELS)
    read_table(session, config)

    # opponent discards one more tile, then we read again
    _fake_screen(monkeypatch, HAND_LABELS, [*PILE_LABELS, "3s"])
    read_table(session, config)

    assert session.table.opponents[1].discards == labels_to_tiles([*PILE_LABELS, "3s"])


def test_read_table_without_calibration_explains_itself(tmp_path, monkeypatch):
    from mahjong_advisor.vision.runner import CalibrationError, read_table

    config = VisionConfig(templates_dir=str(_templates_dir(tmp_path, ["1m"])))
    with pytest.raises(CalibrationError, match="手牌の範囲"):
        read_table(AdvisorSession(), config)


def test_read_table_without_templates_explains_itself(tmp_path):
    from mahjong_advisor.vision.runner import CalibrationError, read_table

    config = VisionConfig(
        hand_region=CaptureRegion(0, 0, 100, 72),
        templates_dir=str(tmp_path / "nothing_here"),
    )
    with pytest.raises(CalibrationError, match="テンプレート"):
        read_table(AdvisorSession(), config)
