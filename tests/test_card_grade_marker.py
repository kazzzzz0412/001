import numpy as np
import pytest
from PIL import Image, ImageDraw

from card_grade_marker import MarkerStyle, detect_chip_row, highlight_grade
from card_grade_marker.__main__ import main

BG = (15, 15, 15)
CHIP_BORDER = (48, 48, 48)
LABEL = (235, 235, 235)
WHITE = (255, 255, 255)

CHIP_TOP, CHIP_BOTTOM = 700, 920
CHIP_WIDTH, CHIP_PITCH, FIRST_LEFT = 240, 270, 40


def make_screenshot(chip_count=5, selected=1, heading=True, width=1290, height=1000):
    """A stand-in for the PSA population screen: a row of bordered chips."""
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)

    if heading:
        # Text-like blocks above the row: ink, but not closed top and bottom.
        for i in range(6):
            x = 60 + i * 46
            draw.rectangle((x, 560 + (i % 3) * 6, x + 38, 604 - (i % 2) * 8), fill=LABEL)

    for i in range(chip_count):
        x0 = FIRST_LEFT + i * CHIP_PITCH
        box = (x0, CHIP_TOP, x0 + CHIP_WIDTH - 1, CHIP_BOTTOM)
        is_selected = i == selected
        draw.rounded_rectangle(
            box,
            radius=48,
            outline=WHITE if is_selected else CHIP_BORDER,
            width=6 if is_selected else 2,
            fill=(33, 33, 33) if is_selected else BG,
        )
        # Every chip carries a white-ish label, selected or not.
        draw.rectangle((x0 + 70, 780, x0 + 170, 800), fill=LABEL)
    return image


def test_detects_every_chip_and_the_selected_one():
    row = detect_chip_row(make_screenshot())

    assert len(row.chips) == 5
    assert row.selected_index() == 1
    assert row.background == BG
    assert row.y0 == pytest.approx(CHIP_TOP, abs=3)
    assert row.y1 == pytest.approx(CHIP_BOTTOM, abs=3)
    for i, chip in enumerate(row.chips):
        left = FIRST_LEFT + i * CHIP_PITCH
        assert chip.x0 == pytest.approx(left, abs=3)
        # The rightmost chip is clipped by the edge of the screen.
        assert chip.width == pytest.approx(min(CHIP_WIDTH, 1290 - left), abs=6)


def test_heading_text_is_not_mistaken_for_the_chip_row():
    # The heading blocks sit above the chips; only the chips are bordered boxes.
    row = detect_chip_row(make_screenshot())
    assert row.y0 > 640


def test_other_chips_are_erased_and_the_target_is_kept():
    image = make_screenshot()
    result, row, index = highlight_grade(image)

    assert index == 1
    before = np.asarray(image)
    after = np.asarray(result)
    target = row.chips[index]

    kept = (slice(row.y0, row.y1 + 1), slice(target.x0, target.x1 + 1))
    assert np.array_equal(after[kept], before[kept])

    # The chip left of the target is far from the arrow: nothing but background.
    untouched = after[row.y0 : row.y1 + 1, row.chips[0].x0 : row.chips[0].x1 + 1]
    assert np.array_equal(np.unique(untouched.reshape(-1, 3), axis=0), np.array([BG]))

    # Chips the arrow crosses are erased too, arrow pixels aside: no label survives.
    band = after[row.y0 : row.y1 + 1].copy()
    band[:, target.x0 : target.x1 + 1] = BG
    assert not (band == LABEL).all(axis=2).any()


def test_arrow_is_drawn_beside_the_target():
    image = make_screenshot(selected=0)
    style = MarkerStyle(arrow_color=(255, 0, 0))
    result, row, index = highlight_grade(image, style=style)

    after = np.asarray(result).astype(int)
    target = row.chips[index]
    right = after[row.y0 : row.y1 + 1, target.x1 + 1 :]
    left = after[row.y0 : row.y1 + 1, : target.x0]
    # Room is on the right for the leftmost chip, so that is where the arrow goes.
    assert (right[:, :, 0] > 200).sum() > 500
    assert (left[:, :, 0] > 200).sum() == 0


def test_side_can_be_forced():
    image = make_screenshot(selected=4)
    result, row, index = highlight_grade(
        image, style=MarkerStyle(arrow_color=(255, 0, 0), side="left")
    )
    after = np.asarray(result).astype(int)
    target = row.chips[index]
    left = after[row.y0 : row.y1 + 1, : target.x0]
    assert (left[:, :, 0] > 200).sum() > 500


def test_fill_color_overrides_the_sampled_background():
    image = make_screenshot()
    result, row, index = highlight_grade(image, style=MarkerStyle(fill_color=(0, 0, 0)))
    after = np.asarray(result)
    erased = after[row.y0 : row.y1 + 1, row.chips[0].x0 : row.chips[0].x1 + 1]
    assert np.array_equal(np.unique(erased.reshape(-1, 3), axis=0), np.array([[0, 0, 0]]))


def test_explicit_target_wins_over_the_selection():
    _, row, index = highlight_grade(make_screenshot(), target=3)
    assert index == 3
    assert row.chips[1].selected is True


def test_without_a_selection_a_target_is_required():
    image = make_screenshot(selected=None)
    with pytest.raises(ValueError, match="--target"):
        highlight_grade(image)
    _, _, index = highlight_grade(image, target=2)
    assert index == 2


def test_target_out_of_range_is_reported():
    with pytest.raises(IndexError):
        highlight_grade(make_screenshot(), target=9)


def test_blank_image_reports_no_chip_row():
    with pytest.raises(ValueError, match="no chip row"):
        detect_chip_row(Image.new("RGB", (400, 400), BG))


def test_band_override_is_used_as_given():
    row = detect_chip_row(make_screenshot(), band=(CHIP_TOP, CHIP_BOTTOM))
    assert (row.y0, row.y1) == (CHIP_TOP, CHIP_BOTTOM)
    assert len(row.chips) == 5


def test_band_override_accepts_a_row_with_one_chip():
    image = make_screenshot(chip_count=1, selected=0)
    row = detect_chip_row(image, band=(CHIP_TOP, CHIP_BOTTOM))
    assert len(row.chips) == 1
    assert row.selected_index() == 0


def test_band_override_with_nothing_in_it_is_reported():
    with pytest.raises(ValueError, match="no chips found"):
        detect_chip_row(make_screenshot(), band=(100, 300))


def test_cli_writes_an_image(tmp_path, capsys):
    source = tmp_path / "shot.png"
    make_screenshot().save(source)
    output = tmp_path / "marked.png"

    assert main([str(source), "-o", str(output)]) == 0
    assert output.exists()
    assert "kept chip 2 of 5" in capsys.readouterr().out


def test_cli_lists_chips(tmp_path, capsys):
    source = tmp_path / "shot.png"
    make_screenshot().save(source)

    assert main([str(source), "--list"]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 6
    assert "<- selected" in out


def test_cli_reports_a_bad_target(tmp_path, capsys):
    source = tmp_path / "shot.png"
    make_screenshot().save(source)

    assert main([str(source), "--target", "9"]) == 1
    assert "out of range" in capsys.readouterr().err
