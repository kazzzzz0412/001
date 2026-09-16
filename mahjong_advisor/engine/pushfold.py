"""押し引き - putting hand value and deal-in risk on the same scale.

Deliberately a transparent heuristic, not a solver. It answers "is pushing this
tile worth more than folding right now?" by comparing:

    EV(push) = win_rate x win_value - accumulated_risk x deal_in_cost
    EV(fold) = a flat penalty for giving the hand up

`accumulated_risk` is the point of the model: pushing one tile commits you to
pushing more tiles on later turns, so a single turn's deal-in chance understates
what pushing actually costs. Every constant below is an approximation from
published riichi statistics and is exposed so you can see what drove a verdict.
"""

from __future__ import annotations

from dataclasses import dataclass

# Win rate of a hand pushed to the end, by shanten and turn (巡目).
_WIN_RATE_ANCHORS: dict[int, list[tuple[int, float]]] = {
    0: [(1, 0.55), (4, 0.50), (7, 0.42), (10, 0.32), (13, 0.20), (16, 0.10), (18, 0.05)],
    1: [(1, 0.33), (4, 0.28), (7, 0.20), (10, 0.12), (13, 0.05), (16, 0.02), (18, 0.00)],
    2: [(1, 0.18), (4, 0.14), (7, 0.08), (10, 0.04), (13, 0.01), (16, 0.00), (18, 0.00)],
    3: [(1, 0.09), (4, 0.06), (7, 0.03), (10, 0.01), (13, 0.00), (16, 0.00), (18, 0.00)],
}

WIN_VALUE_TENPAI = 6500
"""Average value of a closed tenpai hand you can still riichi (incl. ura/tsumo upside)."""
WIN_VALUE_OTHER = 5200

DEAL_IN_COST_RIICHI = 5800
DEAL_IN_COST_SUSPECTED = 5000

AVG_FUTURE_RISK = 0.05
"""Average deal-in chance of each *subsequent* tile you push after this one."""

FOLD_TURN_RISK = 0.008
"""Residual deal-in chance per discard while folding with safe-ish tiles."""

NOTEN_SWING = 1500
"""Point swing between being tenpai and noten at an exhaustive draw."""

RYUUKYOKU_RATE = 0.16
"""How often a hand actually reaches an exhaustive draw."""

_TENPAI_CHANCE_BY_SHANTEN = {0: 1.0, 1: 0.55, 2: 0.25, 3: 0.08}

BORDERLINE_MARGIN = 250
"""EV gap under which the call is too close to matter."""

PUSH = "押し"
FOLD = "オリ"
BORDERLINE = "微妙"


def estimate_win_rate(shanten: int, ukeire_live: int, turn: int) -> float:
    """Chance of winning the hand if pushed to the end."""
    if shanten < 0:
        return 1.0

    anchors = _WIN_RATE_ANCHORS.get(min(shanten, 3), _WIN_RATE_ANCHORS[3])
    turn = max(1, min(turn, 18))

    base = anchors[-1][1]
    for (turn_a, rate_a), (turn_b, rate_b) in zip(anchors, anchors[1:]):
        if turn_a <= turn <= turn_b:
            span = turn_b - turn_a
            ratio = (turn - turn_a) / span if span else 0.0
            base = rate_a + (rate_b - rate_a) * ratio
            break

    if shanten > 3:
        base *= 0.4 ** (shanten - 3)

    # A wide wait wins more often than a dead one at the same shanten.
    if shanten == 0:
        scale = min(1.5, max(0.5, ukeire_live / 6))
    else:
        scale = min(1.4, max(0.6, ukeire_live / 18))
    return base * scale


def expected_future_pushes(shanten: int, turn: int) -> float:
    """How many more dangerous tiles this hand is likely to push after this one."""
    remaining = max(0, 18 - turn)
    commitment = {0: 1.0, 1: 0.8}.get(shanten, 0.6)
    return min(5.0, remaining * 0.5 * commitment)


def accumulated_risk(this_tile_risk: float, shanten: int, turn: int) -> float:
    """Chance of dealing in at some point if you keep pushing this hand."""
    survive = (1.0 - this_tile_risk) * (1.0 - AVG_FUTURE_RISK) ** expected_future_pushes(
        shanten, turn
    )
    return 1.0 - survive


def deal_in_cost(has_riichi: bool) -> int:
    return DEAL_IN_COST_RIICHI if has_riichi else DEAL_IN_COST_SUSPECTED


def tenpai_chance(shanten: int, turn: int) -> float:
    """Chance this hand still reaches tenpai - i.e. what folding gives up."""
    base = _TENPAI_CHANCE_BY_SHANTEN.get(shanten, 0.02)
    if shanten == 0:
        return base
    remaining = max(0, 18 - turn)
    return base * min(1.0, remaining / 12)


def fold_ev(*, safest_tile_risk: float, shanten: int, turn: int, has_riichi: bool) -> float:
    """Expected points from backing out: you still have to discard something
    each turn, and you give up whatever tenpai chance the hand had."""
    remaining = max(0, 18 - turn)
    survive = (1.0 - safest_tile_risk) * (1.0 - FOLD_TURN_RISK) ** min(remaining, 6)
    residual_risk = 1.0 - survive
    forfeited = tenpai_chance(shanten, turn) * NOTEN_SWING * RYUUKYOKU_RATE
    return -residual_risk * deal_in_cost(has_riichi) - forfeited


@dataclass
class PushFoldVerdict:
    verdict: str
    ev_push: float
    ev_fold: float
    safe_tile_available: bool = False
    """True when the top discard carries no risk at all - nothing to decide yet."""

    @property
    def margin(self) -> float:
        return self.ev_push - self.ev_fold


def push_ev(
    *,
    shanten: int,
    ukeire_live: int,
    turn: int,
    this_tile_risk: float,
    has_riichi: bool,
) -> float:
    """Expected point value of pushing this specific tile, in points."""
    win_rate = estimate_win_rate(shanten, ukeire_live, turn)
    win_value = WIN_VALUE_TENPAI if shanten == 0 else WIN_VALUE_OTHER
    risk = accumulated_risk(this_tile_risk, shanten, turn)
    return win_rate * win_value - risk * deal_in_cost(has_riichi)


def decide(
    best_push_ev: float, best_fold_ev: float, safe_tile_available: bool = False
) -> PushFoldVerdict:
    if best_push_ev > best_fold_ev + BORDERLINE_MARGIN:
        verdict = PUSH
    elif best_push_ev < best_fold_ev - BORDERLINE_MARGIN:
        verdict = FOLD
    else:
        verdict = BORDERLINE
    return PushFoldVerdict(
        verdict=verdict,
        ev_push=best_push_ev,
        ev_fold=best_fold_ev,
        safe_tile_available=safe_tile_available,
    )
