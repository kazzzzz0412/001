"""危険牌読み - deal-in risk estimation for a candidate discard.

Rather than a flat lookup table, this enumerates every wait shape that could
ron the tile and asks whether that shape is still possible:

  両面 (ryanmen)  holds {r-2,r-1} waiting {r-3, r}, or {r+1,r+2} waiting {r, r+3}
  辺張 (penchan)  the same shape when the other end falls off the 1-9 range
  嵌張 (kanchan)  holds {r-1, r+1}
  双碰 (shanpon)  holds a pair of the tile
  単騎 (tanki)    holds a single copy of the tile

A shape is ruled out when:

  * the opponent already discarded the tile itself      -> 現物, risk 0
  * the shape's *other* wait is in their discards       -> furiten, i.e. スジ
  * a tile the shape requires has no unseen copies left -> 壁 / ノーチャンス

Surviving shapes are weighted by how often real tenpai hands wait that way and
scaled by how many copies of the required tiles are still unseen. The result is
calibrated so a fully-live no-suji middle tile lands near the ~6.5% deal-in rate
reported for pushing against a riichi. Treat the numbers as calibrated
estimates from a shape-frequency model, not as empirical measurements.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mahjong_advisor.engine.names import tile_notation
from mahjong_advisor.engine.table import Opponent, TableState

HONOR_START = 27
DRAGON_START = 31

# Relative frequency of each wait shape among tenpai hands, per shape instance.
WEIGHT_RYANMEN = 0.24
WEIGHT_PENCHAN = 0.08
WEIGHT_KANCHAN = 0.19
WEIGHT_SHANPON = 0.19
WEIGHT_TANKI = 0.17

# Scales raw shape weight into a deal-in probability. Chosen so that a fully
# live no-suji 4/5/6 against a riichi comes out at ~6.5%.
CALIBRATION = 0.0703

# How often each rank ends up as the *pair* of a shanpon or a tanki wait,
# relative to a middle tile. Real hands keep terminals and honors as pairs far
# more often than they keep 4/5/6 as pairs, which is why a lone honor is more
# dangerous than its run-shape count alone suggests. Applied only to the
# shanpon/tanki part of the estimate - it must not inflate ryanmen risk.
PAIR_BIAS_BY_RANK = {1: 1.85, 2: 1.40, 3: 1.35, 4: 1.0, 5: 1.0, 6: 1.0, 7: 1.35, 8: 1.40, 9: 1.85}
HONOR_PAIR_BIAS = 1.96
YAKUHAI_BIAS = 1.15


def _is_honor(tile: int) -> bool:
    return tile >= HONOR_START


def _rank(tile: int) -> int:
    """1-9 within its suit. Only meaningful for suited tiles."""
    return tile % 9 + 1


def _tile_at(tile: int, rank: int) -> int | None:
    """The tile of the same suit at `rank`, or None if outside 1-9."""
    if rank < 1 or rank > 9:
        return None
    return (tile // 9) * 9 + rank - 1


@dataclass
class OpponentDanger:
    label: str
    probability: float
    """Estimated chance this discard deals in to this opponent, 0.0-1.0."""
    reason: str
    threat: float

    @property
    def is_safe(self) -> bool:
        return self.probability <= 0.0


@dataclass
class DangerReport:
    probability: float
    """Combined chance of dealing in to any threatening opponent."""
    per_opponent: list[OpponentDanger] = field(default_factory=list)

    @property
    def percent(self) -> float:
        return self.probability * 100.0

    @property
    def reason(self) -> str:
        """Reason from the most dangerous opponent, tagged with who they are."""
        if not self.per_opponent:
            return "-"
        worst = max(self.per_opponent, key=lambda d: d.probability)
        return f"{worst.reason}({worst.label})"


def _suji_label(tile: int, shapes_blocked: int, shapes_total: int) -> str:
    if _is_honor(tile):
        return "字牌"
    if shapes_total > 0 and shapes_blocked >= shapes_total:
        return "スジ"
    if shapes_blocked > 0:
        return "片スジ"
    return "無スジ"


def assess_for_opponent(
    tile: int, opponent: Opponent, unseen: list[int], safe_tiles: set[int]
) -> OpponentDanger:
    """Estimate the chance that discarding `tile` deals into `opponent`."""
    threat = opponent.threat

    if tile in safe_tiles:
        reason = "現物" if tile in opponent.discards else "通過"
        return OpponentDanger(opponent.label, 0.0, reason, threat)

    notes: list[str] = []

    # --- shapes that hold the tile itself (単騎 / 双碰) -------------------
    unseen_self = unseen[tile]
    pair_raw = 0.0
    if unseen_self >= 1:
        pair_raw += WEIGHT_TANKI * (unseen_self / 4)
    if unseen_self >= 2:
        pair_raw += WEIGHT_SHANPON * ((unseen_self - 1) / 3)

    # --- shapes built from neighbouring tiles (両面 / 辺張 / 嵌張) --------
    run_raw = 0.0

    ryanmen_shapes = 0
    ryanmen_blocked_by_suji = 0
    one_chance = False
    no_chance = False

    if not _is_honor(tile):
        rank = _rank(tile)

        # --- two-tile run shapes: {r-2,r-1} and {r+1,r+2} ----------------
        for low_rank, other_wait_rank in ((rank - 2, rank - 3), (rank + 1, rank + 3)):
            high_rank = low_rank + 1
            if low_rank < 1 or high_rank > 9:
                continue

            low_tile = _tile_at(tile, low_rank)
            high_tile = _tile_at(tile, high_rank)
            assert low_tile is not None and high_tile is not None

            other_wait = _tile_at(tile, other_wait_rank)
            is_ryanmen = other_wait is not None
            if is_ryanmen:
                ryanmen_shapes += 1
                if other_wait in safe_tiles:
                    # They discarded the shape's other wait -> furiten -> スジ.
                    ryanmen_blocked_by_suji += 1
                    continue

            availability = (unseen[low_tile] / 4) * (unseen[high_tile] / 4)
            if unseen[low_tile] == 0 or unseen[high_tile] == 0:
                no_chance = True
            elif min(unseen[low_tile], unseen[high_tile]) == 1:
                one_chance = True

            run_raw += (WEIGHT_RYANMEN if is_ryanmen else WEIGHT_PENCHAN) * availability

        # --- kanchan {r-1, r+1} ------------------------------------------
        low_tile = _tile_at(tile, rank - 1)
        high_tile = _tile_at(tile, rank + 1)
        if low_tile is not None and high_tile is not None:
            run_raw += WEIGHT_KANCHAN * (unseen[low_tile] / 4) * (unseen[high_tile] / 4)

    # --- pair-holding bias, applied to the shanpon/tanki part only --------
    if _is_honor(tile):
        pair_raw *= HONOR_PAIR_BIAS
        if tile >= DRAGON_START:
            pair_raw *= YAKUHAI_BIAS
        notes.append(f"残り{unseen_self}枚")
    else:
        pair_raw *= PAIR_BIAS_BY_RANK[_rank(tile)]

    probability = max(0.0, (run_raw + pair_raw) * CALIBRATION)

    label = _suji_label(tile, ryanmen_blocked_by_suji, ryanmen_shapes)
    if no_chance:
        notes.insert(0, "ノーチャンス")
    elif one_chance:
        notes.insert(0, "ワンチャンス")
    reason = "・".join([label, *notes])

    return OpponentDanger(opponent.label, probability, reason, threat)


def assess(tile: int, table: TableState, hand_34: list[int]) -> DangerReport:
    """Combined deal-in risk for discarding `tile`, across every threat."""
    unseen = table.unseen_34(hand_34)
    per_opponent: list[OpponentDanger] = []

    for opponent in table.opponents:
        if opponent.threat <= 0:
            continue
        danger = assess_for_opponent(tile, opponent, unseen, table.safe_tiles(opponent))
        # Scale by how likely this opponent is to actually be tenpai.
        danger.probability *= opponent.threat
        per_opponent.append(danger)

    survive = 1.0
    for danger in per_opponent:
        survive *= 1.0 - danger.probability

    return DangerReport(probability=1.0 - survive, per_opponent=per_opponent)


def safe_tile_summary(table: TableState, hand_34: list[int]) -> dict[str, list[str]]:
    """Per-opponent list of tiles in hand that are 100% safe against them."""
    summary: dict[str, list[str]] = {}
    for opponent in table.threatening_opponents():
        safe = table.safe_tiles(opponent)
        in_hand = [tile_notation(t) for t in range(34) if hand_34[t] > 0 and t in safe]
        summary[opponent.label] = in_hand
    return summary
