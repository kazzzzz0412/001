import pytest

from card_lettering import LetterStyle, find_font, line_image

FONT = "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"


def test_a_space_opens_a_wider_gap_than_plain_characters():
    style = LetterStyle()
    font = FONT
    solid = line_image("カイリキー進化系", 120, font, style)
    spaced = line_image("カイリキー 進化系", 120, font, style)
    assert spaced.width > solid.width + round(120 * style.tracking_ratio)


@pytest.mark.parametrize("character", ["イ", "國", "ー"])
def test_characters_sit_one_tracking_apart_whatever_their_width(character):
    # With the font's own margins dropped, spacing goes by ink rather than by
    # advance width: doubling a character adds its own ink plus one gap, for a
    # narrow katakana exactly as for a wide kanji.
    size = 120
    style = LetterStyle(bearing_ratio=0.0)
    font = FONT
    edge = round(size * style.weight_ratio) + round(size * style.outline_ratio)
    one = line_image(character, size, font, style)
    two = line_image(character * 2, size, font, style)

    grown = two.width - one.width
    assert grown == pytest.approx(
        one.width - 2 * edge + round(size * style.tracking_ratio), abs=2
    )


def test_keeping_some_side_margin_gives_narrow_characters_more_air():
    # A katakana carries wider blank margins than a kanji, so the share of them
    # that is kept opens it up more - which is what stops it reading tighter.
    size = 120
    font = FONT

    def added(character: str, bearing: float) -> int:
        style = LetterStyle(bearing_ratio=bearing)
        one = line_image(character, size, font, style)
        two = line_image(character * 2, size, font, style)
        return (two.width - one.width) - one.width

    assert added("イ", 0.45) - added("イ", 0.0) > added("國", 0.45) - added("國", 0.0)


def test_a_missing_font_is_reported(monkeypatch):
    monkeypatch.setattr("card_lettering.lettering.FONT_CANDIDATES", ("/nowhere.ttf",))
    with pytest.raises(FileNotFoundError, match="--font"):
        find_font()
