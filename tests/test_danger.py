import pytest
from mahjong.tile import TilesConverter

from mahjong_advisor.engine.danger import assess, assess_for_opponent, safe_tile_summary
from mahjong_advisor.engine.table import TableState


def idx(notation: str) -> int:
    return TilesConverter.one_line_string_to_34_array(notation).index(1)


def risk(tile: str, discards=(), hand_extra=(), suspected=False) -> float:
    """Deal-in risk of `tile` against one riichi opponent with `discards`."""
    table = TableState()
    for discarded in discards:
        table.discard(2, idx(discarded))
    if suspected:
        table.mark_suspected(2)
    else:
        table.declare_riichi(2)

    hand = [0] * 34
    hand[idx(tile)] += 1
    for extra in hand_extra:
        hand[idx(extra)] += 1

    return assess(idx(tile), table, hand).probability


# --- genbutsu ---------------------------------------------------------------
def test_genbutsu_is_zero_risk():
    assert risk("5m", discards=["5m"]) == 0.0


def test_genbutsu_reason_names_the_opponent():
    table = TableState()
    table.discard(2, idx("5m"))
    table.declare_riichi(2)
    hand = [0] * 34
    hand[idx("5m")] = 1
    report = assess(idx("5m"), table, hand)
    assert report.probability == 0.0
    assert "現物" in report.reason
    assert "対面" in report.reason


def test_tiles_passing_after_riichi_become_safe():
    """A tile another player discarded after the riichi has passed it, so the
    riichi player is furiten on it."""
    table = TableState()
    table.declare_riichi(2)
    table.discard(1, idx("5m"))  # 下家 discards 5m, riichi player did not ron

    hand = [0] * 34
    hand[idx("5m")] = 1
    report = assess(idx("5m"), table, hand)
    assert report.probability == 0.0
    assert "通過" in report.reason


def test_tile_discarded_before_riichi_by_another_player_is_not_safe():
    table = TableState()
    table.discard(1, idx("5m"))  # passed BEFORE the riichi - proves nothing
    table.declare_riichi(2)

    hand = [0] * 34
    hand[idx("5m")] = 1
    assert assess(idx("5m"), table, hand).probability > 0.0


# --- suji -------------------------------------------------------------------
def test_suji_is_safer_than_musuji():
    assert risk("5m", discards=["2m", "8m"]) < risk("5m")


def test_half_suji_sits_between_musuji_and_full_suji():
    musuji = risk("5m")
    half = risk("5m", discards=["2m"])
    full = risk("5m", discards=["2m", "8m"])
    assert full < half < musuji


def test_suji_labels():
    table = TableState()
    for tile in ("2m", "8m"):
        table.discard(2, idx(tile))
    table.declare_riichi(2)
    hand = [0] * 34
    hand[idx("5m")] = 1
    assert "スジ" in assess(idx("5m"), table, hand).reason


# --- walls / no-chance ------------------------------------------------------
def test_no_chance_is_safer_than_musuji():
    """Holding all four 4m kills every ryanmen and kanchan through 4m."""
    assert risk("5m", hand_extra=["4m"] * 4) < risk("5m")


def test_no_chance_is_labelled():
    table = TableState()
    table.declare_riichi(2)
    hand = [0] * 34
    hand[idx("5m")] = 1
    for _ in range(4):
        hand[idx("4m")] += 1
    assert "ノーチャンス" in assess(idx("5m"), table, hand).reason


def test_one_chance_is_between_no_chance_and_musuji():
    assert risk("5m", hand_extra=["4m"] * 4) < risk("5m", hand_extra=["4m"] * 3) < risk("5m")


# --- honors -----------------------------------------------------------------
def test_dead_honor_is_completely_safe():
    """All four copies accounted for - the opponent cannot be holding one."""
    assert risk("1z", hand_extra=["1z"] * 3) == 0.0


def test_honor_gets_safer_as_copies_appear():
    assert risk("1z", hand_extra=["1z", "1z"]) < risk("1z", hand_extra=["1z"]) < risk("1z")


def test_yakuhai_is_more_dangerous_than_a_wind():
    assert risk("7z") > risk("1z")


def test_live_honor_is_safer_than_a_musuji_middle_tile():
    assert risk("1z") < risk("5m")


# --- tile ranks -------------------------------------------------------------
def test_musuji_risk_increases_toward_the_middle():
    assert risk("1m") < risk("2m") < risk("3m") < risk("4m")


def test_calibrated_against_published_deal_in_rates():
    """The model is calibrated to published rates for pushing against a riichi;
    these bounds catch a miscalibration, not small modelling changes."""
    assert 0.060 <= risk("5m") <= 0.070  # 無スジ456 ~6.5%
    assert 0.045 <= risk("1m") <= 0.055  # 無スジ19  ~5.0%
    assert 0.030 <= risk("1z") <= 0.040  # 生牌の客風 ~3.5%
    assert 0.028 <= risk("5m", discards=["2m", "8m"]) <= 0.040  # 中スジ ~3.5%


# --- threat levels ----------------------------------------------------------
def test_suspected_opponent_is_half_as_dangerous_as_riichi():
    assert risk("5m", suspected=True) == pytest.approx(risk("5m") / 2, rel=1e-6)


def test_unmarked_opponent_contributes_no_risk():
    table = TableState()
    table.discard(2, idx("1p"))  # discards recorded, but no riichi and no mark
    hand = [0] * 34
    hand[idx("5m")] = 1
    assert assess(idx("5m"), table, hand).probability == 0.0


def test_two_threats_combine():
    table = TableState()
    table.declare_riichi(1)
    table.declare_riichi(2)
    hand = [0] * 34
    hand[idx("5m")] = 1
    report = assess(idx("5m"), table, hand)
    assert len(report.per_opponent) == 2
    single = risk("5m")
    assert report.probability > single
    assert report.probability == pytest.approx(1 - (1 - single) ** 2, rel=1e-6)


# --- safe tile summary ------------------------------------------------------
def test_safe_tile_summary_lists_genbutsu_in_hand():
    table = TableState()
    for tile in ("1z", "5m"):
        table.discard(2, idx(tile))
    table.declare_riichi(2)

    hand = [0] * 34
    for tile in ("1z", "5m", "3p"):
        hand[idx(tile)] += 1

    summary = safe_tile_summary(table, hand)
    assert summary["対面"] == ["5m", "1z"]


def test_assess_for_opponent_rejects_nothing_when_all_copies_gone():
    """A tile with no unseen copies can still be ronned by a ryanmen wait -
    only the pair-based shapes become impossible."""
    table = TableState()
    table.declare_riichi(2)
    hand = [0] * 34
    hand[idx("5m")] = 4  # I hold every copy of 5m
    unseen = table.unseen_34(hand)
    assert unseen[idx("5m")] == 0

    danger = assess_for_opponent(idx("5m"), table.opponents[1], unseen, set())
    assert danger.probability > 0.0  # ryanmen 34m / 67m can still be waiting
