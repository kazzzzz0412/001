import numpy as np
import pytest
from PIL import Image, ImageDraw

from card_title_overlay import (
    TitleLines,
    TitleStyle,
    add_title,
    find_artwork_band,
    find_card_band,
    split_title,
)
from card_title_overlay.__main__ import main

BACKDROP = (18, 18, 20)
ART_TOP, ART_BOTTOM = 700, 1500
LABEL_TOP, LABEL_BOTTOM = 400, 425


SEAM_TOP, SEAM_BOTTOM = 490, 509
CARD_TOP = 520


def make_photo(width=2576, height=1932, label=True, art=(ART_TOP, ART_BOTTOM)):
    """A stand-in for a photo of slabbed cards on a dark backdrop."""
    image = Image.new("RGB", (width, height), BACKDROP)
    draw = ImageDraw.Draw(image)
    # The slab: mid grey, barely saturated, so not artwork.
    draw.rectangle((150, 250, width - 150, height - 250), fill=(150, 152, 156))
    if label:
        # A grading label, with the red header that makes it colourful.
        draw.rectangle((170, 280, width - 170, SEAM_TOP - 1), fill=(228, 230, 234))
        draw.rectangle((170, LABEL_TOP, width - 170, LABEL_BOTTOM), fill=(214, 44, 52))
        # The slab frame between the label and the card reads as a dark seam.
        draw.rectangle((150, SEAM_TOP, width - 150, SEAM_BOTTOM), fill=(70, 72, 76))
    # The card itself: pale, with a block of saturated yellow for its artwork.
    draw.rectangle((190, CARD_TOP, width - 190, height - 330), fill=(236, 236, 238))
    draw.rectangle((210, art[0], width - 210, art[1]), fill=(236, 178, 46))
    return image


def test_split_title_puts_the_subject_in_the_middle():
    lines = split_title("希少 カイリキー 進化系 eカード 3連番 セット")
    assert lines == TitleLines(top="希少", main="カイリキー 進化系", bottom="eカード 3連番 セット")


@pytest.mark.parametrize(
    "title, expected",
    [
        ("レア", TitleLines(main="レア")),
        ("レア セット", TitleLines(main="レア", bottom="セット")),
        ("希少 カイリキー セット", TitleLines(top="希少", main="カイリキー", bottom="セット")),
        ("", TitleLines()),
    ],
)
def test_split_title_shorter_titles(title, expected):
    assert split_title(title) == expected


def test_artwork_band_is_the_card_faces_not_the_label():
    y0, y1 = find_artwork_band(make_photo())
    assert y0 == pytest.approx(ART_TOP, abs=5)
    assert y1 == pytest.approx(ART_BOTTOM, abs=5)


def test_a_photo_without_artwork_is_reported():
    with pytest.raises(ValueError, match="no card artwork"):
        find_artwork_band(Image.new("RGB", (800, 600), BACKDROP))


def test_the_card_band_starts_below_the_label():
    # A pale card shows little colour outside its illustration, so the band to
    # keep off is found from the slab and the seam under its label instead.
    y0, y1 = find_card_band(make_photo())
    assert SEAM_TOP <= y0 <= SEAM_BOTTOM
    assert y1 > ART_BOTTOM


def test_protecting_the_card_covers_more_than_the_artwork():
    photo = make_photo()
    art = find_artwork_band(photo)
    card = find_card_band(photo)
    assert card[0] < art[0] and card[1] > art[1]


def test_the_whole_card_is_left_untouched_by_default():
    photo = make_photo()
    result, _, band = add_title(photo, "希少 カイリキー 進化系 セット")
    before = np.asarray(photo)
    after = np.asarray(result)
    assert band == find_card_band(photo)
    assert np.array_equal(after[band[0] : band[1] + 1], before[band[0] : band[1] + 1])


def test_an_unknown_protect_is_reported():
    with pytest.raises(ValueError, match="protect must be"):
        add_title(make_photo(), "希少 カイリキー セット", protect="slab")


def test_without_a_seam_the_band_starts_at_the_top_of_the_subject():
    # No label at all: there is no trough to cut at, so nothing is given away.
    photo = make_photo(label=False)
    y0, _ = find_card_band(photo)
    assert y0 == pytest.approx(250, abs=6)


def test_the_artwork_is_left_untouched():
    photo = make_photo()
    result, _, band = add_title(
        photo, "希少 カイリキー 進化系 eカード 3連番 セット", protect="art"
    )

    before = np.asarray(photo)
    after = np.asarray(result)
    assert np.array_equal(after[band[0] : band[1] + 1], before[band[0] : band[1] + 1])


def test_text_lands_above_and_below_the_cards():
    photo = make_photo()
    result, _, band = add_title(
        photo, "希少 カイリキー 進化系 eカード 3連番 セット", protect="art"
    )
    after = np.asarray(result).astype(int)

    def painted(rows):
        patch = after[rows]
        red = (patch[..., 0] > 150) & (patch[..., 1] < 110) & (patch[..., 2] < 110)
        return int(red.sum())

    assert painted(slice(0, band[0])) > 20000
    assert painted(slice(band[1] + 1, after.shape[0])) > 20000


def test_the_label_may_be_crossed():
    # The big line is allowed over the grading label; only artwork is protected.
    photo = make_photo()
    result, _, _ = add_title(photo, "希少 カイリキー 進化系 eカード 3連番 セット")
    after = np.asarray(result)
    strip = after[LABEL_TOP : LABEL_BOTTOM + 1]
    assert (strip == 255).all(axis=2).any()


def test_lines_can_be_given_directly():
    photo = make_photo()
    _, lines, _ = add_title(photo, TitleLines(top="", main="カイリキー", bottom="セット"))
    assert lines.main == "カイリキー"


def test_an_empty_title_is_reported():
    with pytest.raises(ValueError, match="title is empty"):
        add_title(make_photo(), "   ")


def test_text_shrinks_to_fit_a_cramped_photo():
    # Cards nearly filling the frame leave thin bands; the text must still fit.
    photo = make_photo(art=(200, 1800))
    result, _, band = add_title(photo, "希少 カイリキー 進化系 eカード 3連番 セット")
    after = np.asarray(result)
    before = np.asarray(photo)
    assert np.array_equal(after[band[0] : band[1] + 1], before[band[0] : band[1] + 1])
    assert not np.array_equal(after, before)


def test_band_override_is_used_as_given():
    photo = make_photo()
    _, _, band = add_title(photo, "希少 カイリキー セット", band=(600, 1600))
    assert band == (600, 1600)


def test_colors_can_be_changed():
    photo = make_photo()
    style = TitleStyle(fill=(0, 0, 0), outline=(0, 128, 255))
    result, _, _ = add_title(photo, "希少 カイリキー セット", style=style)
    after = np.asarray(result).astype(int)
    blue = (after[..., 2] > 200) & (after[..., 0] < 80)
    assert blue.sum() > 10000


def test_cli_writes_an_image(tmp_path, capsys):
    source = tmp_path / "cards.jpg"
    make_photo(width=1288, height=966, art=(350, 750)).save(source)
    output = tmp_path / "out.jpg"

    assert main([str(source), "希少 カイリキー 進化系 セット", "-o", str(output)]) == 0
    assert output.exists()
    assert "artwork rows" in capsys.readouterr().out


def test_cli_show_reports_the_layout(tmp_path, capsys):
    source = tmp_path / "cards.jpg"
    make_photo(width=1288, height=966, art=(350, 750)).save(source)

    assert main([str(source), "希少 カイリキー 進化系 セット", "--show"]) == 0
    out = capsys.readouterr().out
    assert "main:   'カイリキー 進化系'" in out


def test_cli_reports_a_photo_it_cannot_read(tmp_path, capsys):
    missing = tmp_path / "nope.jpg"
    assert main([str(missing), "タイトル"]) == 1
    assert "cannot open" in capsys.readouterr().err
