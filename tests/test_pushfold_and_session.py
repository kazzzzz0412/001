import pytest
from mahjong.tile import TilesConverter

from mahjong_advisor.engine import pushfold
from mahjong_advisor.engine.advisor import STANCE_FOLD, STANCE_PUSH, Advisor
from mahjong_advisor.engine.table import TableState
from mahjong_advisor.session import AdvisorSession, parse_tiles_ordered


def idx(notation: str) -> int:
    return TilesConverter.one_line_string_to_34_array(notation).index(1)


def hand_counts(*tiles: str) -> list[int]:
    counts = [0] * 34
    for tile in tiles:
        counts[idx(tile)] += 1
    return counts


TENPAI = hand_counts(
    "2m", "3m", "4m", "5m", "6m", "7m", "2p", "3p", "4p", "5s", "5s", "7s", "8s", "9m"
)
ONE_SHANTEN = hand_counts(
    "2m", "3m", "4m", "5m", "6m", "9m", "9m", "4p", "4p", "5s", "6s", "7s", "1z", "1z"
)
FAR = hand_counts(
    "1m", "5m", "9m", "2p", "5p", "8p", "3s", "6s", "9s", "1z", "2z", "3z", "4z", "5z"
)


def riichi_table(turn: int = 9) -> TableState:
    table = TableState()
    table.turn = turn
    for tile in ("1z", "9p", "2m", "5m"):
        table.discard(2, idx(tile))
    table.declare_riichi(2)
    return table


# --- push/fold primitives ---------------------------------------------------
def test_win_rate_falls_as_the_hand_gets_further_from_tenpai():
    assert (
        pushfold.estimate_win_rate(0, 8, 6)
        > pushfold.estimate_win_rate(1, 8, 6)
        > pushfold.estimate_win_rate(2, 8, 6)
    )


def test_win_rate_falls_as_turns_run_out():
    assert pushfold.estimate_win_rate(1, 18, 4) > pushfold.estimate_win_rate(1, 18, 14)


def test_accumulated_risk_exceeds_this_turn_alone():
    """Pushing one tile commits you to pushing more later."""
    assert pushfold.accumulated_risk(0.05, shanten=0, turn=6) > 0.05


def test_accumulated_risk_shrinks_late_in_the_hand():
    assert pushfold.accumulated_risk(0.05, 0, 16) < pushfold.accumulated_risk(0.05, 0, 6)


def test_folding_costs_more_when_the_hand_was_tenpai():
    tenpai_fold = pushfold.fold_ev(safest_tile_risk=0.0, shanten=0, turn=8, has_riichi=True)
    far_fold = pushfold.fold_ev(safest_tile_risk=0.0, shanten=4, turn=8, has_riichi=True)
    assert tenpai_fold < far_fold


# --- verdicts ---------------------------------------------------------------
def test_tenpai_pushes_against_a_riichi():
    result = Advisor().analyze(TENPAI, table=riichi_table())
    assert result.push_fold.verdict == pushfold.PUSH


def test_hopeless_hand_folds_against_a_riichi():
    result = Advisor().analyze(FAR, table=riichi_table())
    assert result.push_fold.verdict == pushfold.FOLD


def test_verdict_reports_that_a_genbutsu_is_available():
    result = Advisor().analyze(ONE_SHANTEN, table=riichi_table())
    assert result.push_fold.safe_tile_available
    assert result.best.danger_percent == 0.0


def test_no_threat_means_no_danger_analysis():
    table = TableState()
    table.turn = 9
    result = Advisor().analyze(ONE_SHANTEN, table=table)
    assert result.push_fold is None
    assert result.best.danger is None


# --- stance -----------------------------------------------------------------
def test_fold_stance_ranks_by_safety():
    result = Advisor().analyze(TENPAI, table=riichi_table(), stance=STANCE_FOLD)
    dangers = [option.danger_percent for option in result.discard_options]
    assert dangers == sorted(dangers)
    assert result.best.danger_percent == 0.0


def test_push_stance_ranks_by_efficiency_ignoring_danger():
    result = Advisor().analyze(TENPAI, table=riichi_table(), stance=STANCE_PUSH)
    shantens = [option.shanten_after for option in result.discard_options]
    assert shantens == sorted(shantens)


def test_fold_stance_still_reports_the_honest_verdict():
    """Choosing to fold shouldn't rewrite what the engine actually thinks."""
    result = Advisor().analyze(TENPAI, table=riichi_table(), stance=STANCE_FOLD)
    assert result.push_fold.verdict == pushfold.PUSH


# --- tile parsing -----------------------------------------------------------
def test_parse_tiles_preserves_order():
    assert parse_tiles_ordered("3s1z") == [idx("3s"), idx("1z")]


def test_parse_tiles_handles_red_five():
    assert parse_tiles_ordered("0p") == [idx("5p")]


def test_parse_tiles_rejects_unknown_characters():
    with pytest.raises(ValueError, match="解釈できない文字"):
        parse_tiles_ordered("5x")


def test_parse_tiles_rejects_digits_without_a_suit():
    with pytest.raises(ValueError, match="牌の種類"):
        parse_tiles_ordered("123")


def test_parse_tiles_rejects_out_of_range_honor():
    with pytest.raises(ValueError, match="字牌"):
        parse_tiles_ordered("9z")


# --- session commands -------------------------------------------------------
def test_session_records_opponent_discards():
    session = AdvisorSession()
    session.handle("d2 1z9p")
    assert session.table.opponents[1].discards == [idx("1z"), idx("9p")]


def test_session_round_command_spreads_across_opponents():
    session = AdvisorSession()
    session.handle("d 5p 3s 1z")
    assert session.table.opponents[0].discards == [idx("5p")]
    assert session.table.opponents[1].discards == [idx("3s")]
    assert session.table.opponents[2].discards == [idx("1z")]


def test_session_riichi_marks_threat():
    session = AdvisorSession()
    session.handle("r2")
    assert session.table.opponents[1].is_riichi
    assert session.table.opponents[1].threat == 1.0


def test_session_suspect_and_clear():
    session = AdvisorSession()
    session.handle("w3")
    assert session.table.opponents[2].threat == 0.5
    session.handle("w3 off")
    assert session.table.opponents[2].threat == 0.0


def test_session_turn_is_clamped():
    session = AdvisorSession()
    session.handle("t 99")
    assert session.table.turn == 18


def test_session_stance_switch():
    session = AdvisorSession()
    session.handle("fold")
    assert session.stance == STANCE_FOLD


def test_session_reset_clears_everything():
    session = AdvisorSession()
    session.handle("d2 1z")
    session.handle("r2")
    session.handle("t 12")
    session.handle("reset")
    assert session.table.opponents[1].discards == []
    assert not session.table.opponents[1].is_riichi
    assert session.table.turn == 1


def test_session_analyzes_a_hand_with_danger_after_a_riichi():
    session = AdvisorSession()
    session.handle("t 9")
    session.handle("d2 1z9p2m5m")
    session.handle("r2")
    output = session.handle("2345699m44p567s11z")
    assert "切るなら" in output
    assert "危険度" in output
    assert "現物" in output


def test_session_rejects_a_wrong_sized_hand_in_japanese():
    session = AdvisorSession()
    assert "13枚か14枚" in session.handle("123m")


def test_session_state_report():
    session = AdvisorSession()
    session.handle("r2")
    session.handle("d2 1z")
    state = session.describe_state()
    assert "リーチ" in state
    assert "1z" in state
