from mahjong_advisor.engine.advisor import Advisor
from mahjong_advisor.engine.names import tile_notation


def idx(notation: str) -> int:
    """Helper: mpsz single-tile notation -> 34-index, for readable assertions."""
    from mahjong.tile import TilesConverter

    arr = TilesConverter.one_line_string_to_34_array(notation)
    return arr.index(1)


def test_agari_hand_detected():
    advisor = Advisor()
    # 123m 456m 789m 123p 11s -> 4 sets + pair, complete (14 tiles).
    result = advisor.analyze("123456789m123p11s")
    assert result.hand_size == 14
    assert result.is_agari is True
    assert result.discard_options == []


def test_13_tile_tenpai_reports_wait():
    advisor = Advisor()
    # 123 456 789m 123p + lone 1s -> tenpai, waiting on 1s (tanki pair wait).
    result = advisor.analyze("123456789m123p1s")
    assert result.hand_size == 13
    assert result.is_tenpai
    assert result.waits == [idx("1s")]


def test_14_tile_best_discard_reaches_tanki_tenpai():
    advisor = Advisor()
    # Same tenpai shape as above, plus an unrelated isolated 9s tile: discarding
    # either lone terminal (1s or 9s) keeps a tanki wait on the other one.
    result = advisor.analyze("123456789m123p1s9s")
    assert result.hand_size == 14
    best = result.best
    assert best is not None
    assert best.tenpai
    assert best.ukeire_kinds == 1
    assert {best.tile, best.ukeire_tiles[0]} == {idx("1s"), idx("9s")}


def test_discard_ranking_prefers_lower_shanten():
    advisor = Advisor()
    # 14-tile hand: discarding the fully isolated 9s reaches tenpai (shanten 0),
    # strictly better than every other discard, which stays at 1-shanten.
    result = advisor.analyze("22345678m123p11z9s")
    assert result.hand_size == 14
    best = result.discard_options[0]
    assert best.tile == idx("9s")
    assert best.shanten_after == 0
    assert all(o.shanten_after >= 0 for o in result.discard_options)
    assert all(o.shanten_after >= best.shanten_after for o in result.discard_options[1:])
    # exactly one candidate reaches shanten 0; the rest are strictly worse
    assert sum(1 for o in result.discard_options if o.shanten_after == 0) == 1


def test_ukeire_live_counts_remaining_copies_not_in_hand():
    advisor = Advisor()
    hand = "123456789m123p1s9s"
    # Hand already holds one of each terminal; with nothing else visible, 3 of
    # whichever tile stays as the tanki wait remain live.
    result = advisor.analyze(hand)
    best = result.best
    assert best.ukeire_live == 3


def test_visible_tiles_reduce_live_count():
    advisor = Advisor()
    hand = "123456789m123p1s9s"
    # All 3 other copies of 1s are already out on the table (discards/dora
    # ind.), so waiting on 1s would be dead. The advisor should prefer
    # discarding the now-dead 1s and keeping the live 9s tanki wait instead.
    visible = "1s1s1s"
    result = advisor.analyze(hand, visible=visible)
    best = result.best
    assert best.tile == idx("1s")
    assert best.ukeire_tiles == [idx("9s")]
    assert best.ukeire_live == 3

    # Sanity: the mirror-image option (discard 9s, wait on the dead 1s) is
    # ranked worse because it shows 0 live tiles even though shanten ties.
    worst = next(o for o in result.discard_options if o.tile == idx("9s"))
    assert worst.ukeire_live == 0


def test_invalid_hand_size_raises():
    advisor = Advisor()
    try:
        advisor.analyze("123m")  # only 3 tiles
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_tile_notation_roundtrip():
    assert tile_notation(0) == "1m"
    assert tile_notation(8) == "9m"
    assert tile_notation(9) == "1p"
    assert tile_notation(26) == "9s"
    assert tile_notation(27) == "1z"
    assert tile_notation(33) == "7z"
