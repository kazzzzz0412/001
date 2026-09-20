from datetime import date

import numpy as np
import pytest
from PIL import Image

from card_stat_stamp import StampStyle, StampText, add_stamp, format_stamp
from card_stat_stamp.__main__ import main

WIDTH, HEIGHT = 1438, 2400


def make_photo(width=WIDTH, height=HEIGHT):
    """A stand-in for a slab photo: plain enough to find the stamp on."""
    return Image.new("RGB", (width, height), (40, 30, 60))


def outline_rows(image):
    a = np.asarray(image).astype(int)
    red = (a[..., 0] > 160) & (a[..., 1] < 90) & (a[..., 2] < 90)
    return red


def line_boxes(image, min_pixels=200):
    red = outline_rows(image)
    rows = np.flatnonzero(red.sum(axis=1) > 3)
    boxes = []
    start = previous = rows[0]
    for y in rows[1:]:
        if y > previous + 12:
            boxes.append((start, previous))
            start = y
        previous = y
    boxes.append((start, previous))
    out = []
    for y0, y1 in boxes:
        cols = np.flatnonzero(red[y0 : y1 + 1].sum(axis=0) > 0)
        if red[y0 : y1 + 1].sum() < min_pixels:
            continue
        out.append((y0, y1, int(cols.min()), int(cols.max())))
    return out


def test_format_stamp_words_the_three_lines():
    text = format_stamp(10, 176, date(2026, 9, 20))
    assert text == StampText(grade="PSA10", pop="POP 176", date="2026/09/20 時点")


@pytest.mark.parametrize("grade", ["10", 10, "PSA10", "psa 10", " PSA 10 "])
def test_grade_is_normalised(grade):
    assert format_stamp(grade=grade).grade == "PSA10"


def test_a_date_string_is_accepted_either_way_round():
    assert format_stamp(when="2026-09-20").date == "2026/09/20 時点"
    assert format_stamp(when="2026/09/20").date == "2026/09/20 時点"


def test_missing_parts_are_left_out():
    text = format_stamp(pop=176)
    assert text.grade == ""
    assert text.date == ""
    assert text.pop == "POP 176"


def test_all_three_lines_are_drawn():
    photo = make_photo()
    result = add_stamp(photo, format_stamp(10, 176, date(2026, 9, 20)))
    assert len(line_boxes(result)) == 3


def test_the_grade_and_population_are_centred_and_the_date_is_not():
    photo = make_photo()
    result = add_stamp(photo, format_stamp(10, 176, date(2026, 9, 20)))
    grade, pop, stamped = line_boxes(result)

    for line in (grade, pop):
        assert (line[2] + line[3]) / 2 == pytest.approx(WIDTH / 2, abs=4)
    assert stamped[3] == pytest.approx(WIDTH * (1 - StampStyle().date_margin), abs=6)


def test_the_population_line_is_the_biggest():
    photo = make_photo()
    result = add_stamp(photo, format_stamp(10, 176, date(2026, 9, 20)))
    grade, pop, stamped = line_boxes(result)
    assert pop[1] - pop[0] > grade[1] - grade[0] > stamped[1] - stamped[0]


def test_lines_land_where_the_style_says():
    photo = make_photo()
    style = StampStyle()
    result = add_stamp(photo, format_stamp(10, 176, date(2026, 9, 20)), style=style)
    grade, _, stamped = line_boxes(result)
    assert grade[0] == pytest.approx(HEIGHT * style.block_top, abs=4)
    assert stamped[0] == pytest.approx(HEIGHT * style.date_top, abs=4)


def test_dropping_a_line_leaves_the_others():
    photo = make_photo()
    result = add_stamp(photo, format_stamp(10, 176))
    assert len(line_boxes(result)) == 2


def test_nothing_to_stamp_is_reported():
    with pytest.raises(ValueError, match="nothing to stamp"):
        add_stamp(make_photo(), format_stamp())


def test_colors_can_be_changed():
    photo = make_photo()
    style = StampStyle(fill=(0, 0, 0), outline=(255, 210, 0))
    result = add_stamp(photo, format_stamp(10, 176), style=style)
    a = np.asarray(result).astype(int)
    assert ((a[..., 0] > 200) & (a[..., 1] > 170) & (a[..., 2] < 90)).sum() > 5000


def test_a_long_population_shrinks_to_fit():
    photo = make_photo()
    wide = add_stamp(photo, format_stamp(pop="123456789012"))
    assert line_boxes(wide)[0][3] - line_boxes(wide)[0][2] <= round(
        WIDTH * StampStyle().line_width
    )


def test_cli_writes_an_image(tmp_path, capsys):
    source = tmp_path / "slab.jpg"
    make_photo(719, 1200).save(source)
    output = tmp_path / "out.jpg"

    assert main([str(source), "--grade", "10", "--pop", "176", "-o", str(output)]) == 0
    assert output.exists()
    out = capsys.readouterr().out
    assert "PSA10 / POP 176 /" in out


def test_cli_can_leave_the_date_off(tmp_path, capsys):
    source = tmp_path / "slab.jpg"
    make_photo(719, 1200).save(source)

    assert main([str(source), "--grade", "10", "--pop", "176", "--no-date"]) == 0
    assert "PSA10 / POP 176 / -" in capsys.readouterr().out


def test_cli_needs_something_to_stamp(tmp_path, capsys):
    source = tmp_path / "slab.jpg"
    make_photo(719, 1200).save(source)

    assert main([str(source), "--no-date"]) == 1
    assert "nothing to stamp" in capsys.readouterr().err


def test_cli_reports_a_photo_it_cannot_read(tmp_path, capsys):
    assert main([str(tmp_path / "nope.jpg"), "--grade", "10"]) == 1
    assert "cannot open" in capsys.readouterr().err
