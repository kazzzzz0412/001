import numpy as np
import pytest
from PIL import Image, ImageDraw

from card_grade_marker import MarkerStyle
from card_grade_marker.__main__ import main
from card_grade_marker.table import find_table, mark_table

BG = (15, 15, 15)
TINT = (29, 29, 29)
RULE = (48, 48, 48)
INK = (250, 250, 250)

WIDTH, HEIGHT = 1290, 1540
X0, X1 = 48, 1241
DIVIDER = (443, 445)
TABLE_TOP = 423
HEADER_HEIGHT = 127
ROW_HEIGHT = 130
RULE_HEIGHT = 2


def make_table(rows=6, divider_line=True):
    """A stand-in for the app's population table on its dark page."""
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    if divider_line:
        # The tab bar's divider runs the whole width, unlike the table's rules.
        draw.rectangle((0, 360, WIDTH - 1, 361), fill=RULE)

    def rule(y):
        draw.rectangle((X0, y, X1, y + RULE_HEIGHT - 1), fill=RULE)
        return y + RULE_HEIGHT

    y = rule(TABLE_TOP)
    draw.rectangle((X0, y, X1, y + HEADER_HEIGHT - 1), fill=TINT)
    y = rule(y + HEADER_HEIGHT)

    for _ in range(rows):
        draw.rectangle((X0, y, DIVIDER[1], y + ROW_HEIGHT - 1), fill=TINT)
        # A grade in the first column and a count in the second.
        draw.rectangle((100, y + 40, 160, y + 90), fill=INK)
        draw.rectangle((495, y + 40, 560, y + 90), fill=INK)
        y = rule(y + ROW_HEIGHT)

    draw.rectangle((X0, y, X1, y + ROW_HEIGHT - 1), fill=RULE)
    # The table's own left and right borders.
    draw.rectangle((X0, TABLE_TOP, X0 + 2, y + ROW_HEIGHT - 1), fill=RULE)
    draw.rectangle((X1 - 2, TABLE_TOP, X1, y + ROW_HEIGHT - 1), fill=RULE)
    draw.rectangle((DIVIDER[0], TABLE_TOP, DIVIDER[1], y + ROW_HEIGHT - 1), fill=RULE)
    return image


def test_the_table_is_found_with_its_rows():
    table = find_table(make_table())

    assert (table.x0, table.x1) == (X0, X1)
    kinds = [row.kind for row in table.rows]
    assert kinds[0] == "header"
    assert kinds[-1] == "total"
    assert len(table.grades) == 6


def test_a_full_width_divider_is_not_taken_for_a_rule():
    with_line = find_table(make_table(divider_line=True))
    without = find_table(make_table(divider_line=False))
    assert [row.kind for row in with_line.rows] == [row.kind for row in without.rows]
    assert with_line.rows[0].y0 == without.rows[0].y0


def test_a_screenshot_with_no_table_is_reported():
    with pytest.raises(ValueError, match="no table"):
        find_table(Image.new("RGB", (400, 400), BG))


@pytest.mark.parametrize("keep", [0, 3, 5])
def test_every_other_grade_row_is_wiped(keep):
    photo = make_table()
    table = find_table(photo)
    result = mark_table(photo, table, keep, MarkerStyle())

    before = np.asarray(photo).astype(int)
    after = np.asarray(result).astype(int)
    for i, row in enumerate(table.grades):
        band = after[row.y0 : row.y1 + 1, X0 + 4 : X1 - 3]
        has_ink = bool((band > 200).all(axis=2).any())
        assert has_ink == (i == keep), f"row {i} ink={has_ink}"

    # The header and the 合計 row are left alone.
    for row in table.rows:
        if row.kind == "grade":
            continue
        assert np.array_equal(
            after[row.y0 : row.y1 + 1], before[row.y0 : row.y1 + 1]
        )


def test_the_kept_row_is_marked():
    photo = make_table()
    table = find_table(photo)
    style = MarkerStyle(arrow_color=(255, 0, 0))
    kept = table.grades[2]

    for mark in ("ring", "arrow"):
        after = np.asarray(mark_table(photo, table, 2, style, mark=mark)).astype(int)
        band = after[kept.y0 : kept.y1 + 1]
        assert ((band[..., 0] > 200) & (band[..., 1] < 90)).sum() > 500


def test_the_arrow_does_not_cover_the_count():
    photo = make_table()
    table = find_table(photo)
    kept = table.grades[0]
    after = np.asarray(
        mark_table(photo, table, 0, MarkerStyle(arrow_color=(255, 0, 0)), mark="arrow")
    ).astype(int)

    count = after[kept.y0 : kept.y1 + 1, 495:561]
    assert (count > 200).all(axis=2).any()


def test_an_unknown_mark_is_reported():
    photo = make_table()
    with pytest.raises(ValueError, match="mark must be"):
        mark_table(photo, find_table(photo), 0, MarkerStyle(), mark="circle")


def test_a_row_out_of_range_is_reported():
    photo = make_table()
    with pytest.raises(IndexError):
        mark_table(photo, find_table(photo), 9, MarkerStyle())


def test_cli_lists_the_table(tmp_path, capsys):
    source = tmp_path / "table.png"
    make_table().save(source)

    assert main([str(source), "--list"]) == 0
    out = capsys.readouterr().out
    assert "table: x 48-1241" in out
    assert "grade row 6" in out
    assert "total:" in out


def test_cli_keeps_the_named_row(tmp_path, capsys):
    source = tmp_path / "table.png"
    make_table().save(source)
    output = tmp_path / "out.png"

    assert main([str(source), "--row", "1", "-o", str(output)]) == 0
    assert output.exists()
    assert "kept grade row 1 of 6" in capsys.readouterr().out


def test_cli_asks_for_a_row_on_a_table(tmp_path, capsys):
    source = tmp_path / "table.png"
    make_table().save(source)

    assert main([str(source)]) == 1
    assert "--row" in capsys.readouterr().err
