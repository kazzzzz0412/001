"""Discard-efficiency advisor built on the `mahjong` package's Shanten calculator.

Scope: this ranks discards by shanten / ukeire (tile-acceptance) only. It is a
speed/efficiency assistant, not a full deal-in-risk or expected-value solver.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from mahjong.shanten import Shanten
from mahjong.tile import TilesConverter

from mahjong_advisor.engine import pushfold
from mahjong_advisor.engine.danger import DangerReport, assess, safe_tile_summary
from mahjong_advisor.engine.names import tile_name, tile_notation
from mahjong_advisor.engine.pushfold import PushFoldVerdict
from mahjong_advisor.engine.table import TableState

HandLike = str | Sequence[int]

STANCE_AUTO = "auto"
STANCE_PUSH = "push"
STANCE_FOLD = "fold"


def _to_34(hand: HandLike) -> list[int]:
    if isinstance(hand, str):
        return TilesConverter.one_line_string_to_34_array(hand, has_aka_dora=True)
    arr = list(hand)
    if len(arr) != 34:
        raise ValueError(f"34-format array must have length 34, got {len(arr)}")
    return arr


@dataclass
class DiscardOption:
    tile: int
    """34-index of the candidate discard."""
    shanten_after: int
    ukeire_tiles: list[int] = field(default_factory=list)
    """34-indices of tile types that would improve shanten if drawn next."""
    ukeire_kinds: int = 0
    """Number of distinct accepting tile types (classic 'ukeire' count)."""
    ukeire_live: int = 0
    """Sum of remaining live copies of accepting tiles, given visible tiles."""
    danger: DangerReport | None = None
    """Deal-in risk, present only when someone at the table is threatening."""
    ev: float | None = None
    """Expected points from pushing this tile, when danger is being weighed."""

    @property
    def danger_percent(self) -> float:
        return self.danger.percent if self.danger else 0.0

    @property
    def danger_reason(self) -> str:
        return self.danger.reason if self.danger else "-"

    @property
    def tenpai(self) -> bool:
        return self.shanten_after == Shanten.TENPAI_STATE

    @property
    def name(self) -> str:
        return tile_notation(self.tile)

    @property
    def display_name(self) -> str:
        return tile_name(self.tile)

    def ukeire_names(self) -> list[str]:
        return [tile_notation(t) for t in self.ukeire_tiles]


@dataclass
class HandAnalysis:
    hand_size: int
    shanten: int
    is_agari: bool = False
    discard_options: list[DiscardOption] = field(default_factory=list)
    """Only populated for 14-tile hands, best option first."""
    waits: list[int] = field(default_factory=list)
    """Only populated for a 13-tile hand that is already tenpai."""
    push_fold: PushFoldVerdict | None = None
    """Push-or-fold call, present only when someone is threatening."""
    stance: str = STANCE_AUTO
    safe_tiles: dict[str, list[str]] = field(default_factory=dict)
    """Per-opponent list of tiles in hand that are 100% safe against them."""

    @property
    def under_threat(self) -> bool:
        return self.push_fold is not None

    @property
    def is_tenpai(self) -> bool:
        return self.shanten == Shanten.TENPAI_STATE

    @property
    def best(self) -> DiscardOption | None:
        return self.discard_options[0] if self.discard_options else None

    def wait_names(self) -> list[str]:
        return [tile_notation(t) for t in self.waits]


class Advisor:
    """Computes shanten/ukeire-ranked discard suggestions for a hand."""

    def analyze(
        self,
        hand: HandLike,
        visible: HandLike | None = None,
        table: TableState | None = None,
        stance: str = STANCE_AUTO,
    ) -> HandAnalysis:
        hand_34 = _to_34(hand)
        hand_size = sum(hand_34)
        if hand_size not in (13, 14):
            raise ValueError(f"Hand must have 13 or 14 tiles (got {hand_size}).")
        for i, c in enumerate(hand_34):
            if c > 4:
                raise ValueError(f"Tile {tile_notation(i)} appears {c} times (max 4).")

        if table is not None:
            visible_34 = table.board_visible_34()
        elif visible is not None:
            visible_34 = _to_34(visible)
        else:
            visible_34 = [0] * 34

        base_shanten = Shanten.calculate_shanten(hand_34)

        if hand_size == 14:
            if base_shanten == Shanten.AGARI_STATE:
                return HandAnalysis(hand_size=hand_size, shanten=base_shanten, is_agari=True)

            options = self._rank_discards(hand_34, visible_34)
            under_threat = table is not None and table.has_threat
            verdict = None
            safe_tiles: dict[str, list[str]] = {}

            if under_threat:
                self._attach_danger(options, hand_34, table)
                verdict = self._resolve_push_fold(options, table)
                safe_tiles = safe_tile_summary(table, hand_34)
                self._sort_with_danger(options, stance, verdict)

            best_shanten = options[0].shanten_after if options else base_shanten
            return HandAnalysis(
                hand_size=hand_size,
                shanten=min(o.shanten_after for o in options) if options else best_shanten,
                discard_options=options,
                push_fold=verdict,
                stance=stance,
                safe_tiles=safe_tiles,
            )

        # 13-tile hand: report current shanten, and waits if already tenpai.
        waits: list[int] = []
        if base_shanten == Shanten.TENPAI_STATE:
            waits = self._accepting_tiles(hand_34, base_shanten)
        return HandAnalysis(hand_size=hand_size, shanten=base_shanten, waits=waits)

    # -- danger / push-fold -------------------------------------------------
    @staticmethod
    def _attach_danger(
        options: list[DiscardOption], hand_34: list[int], table: TableState
    ) -> None:
        has_riichi = any(o.is_riichi for o in table.threatening_opponents())
        for option in options:
            option.danger = assess(option.tile, table, hand_34)
            option.ev = pushfold.push_ev(
                shanten=option.shanten_after,
                ukeire_live=option.ukeire_live,
                turn=table.turn,
                this_tile_risk=option.danger.probability,
                has_riichi=has_riichi,
            )

    @staticmethod
    def _resolve_push_fold(options: list[DiscardOption], table: TableState) -> PushFoldVerdict:
        best_ev = max(o.ev for o in options if o.ev is not None)
        safest = min(options, key=lambda o: o.danger_percent)
        has_riichi = any(o.is_riichi for o in table.threatening_opponents())
        best_shanten = min(o.shanten_after for o in options)

        ev_fold = pushfold.fold_ev(
            safest_tile_risk=safest.danger.probability if safest.danger else 0.0,
            shanten=best_shanten,
            turn=table.turn,
            has_riichi=has_riichi,
        )
        return pushfold.decide(
            best_ev, ev_fold, safe_tile_available=safest.danger_percent <= 0.0
        )

    @staticmethod
    def _sort_with_danger(
        options: list[DiscardOption], stance: str, verdict: PushFoldVerdict
    ) -> None:
        if stance == STANCE_PUSH:
            return  # already ranked by pure efficiency

        folding = stance == STANCE_FOLD or (
            stance == STANCE_AUTO and verdict.verdict == pushfold.FOLD
        )
        if folding:
            # Safety first; among equally safe tiles keep the better hand.
            options.sort(key=lambda o: (o.danger_percent, o.shanten_after, -o.ukeire_live))
        else:
            options.sort(key=lambda o: (-(o.ev or 0.0), o.danger_percent))

    @staticmethod
    def _accepting_tiles(hand_34: list[int], base_shanten: int) -> list[int]:
        accepting = []
        for t in range(34):
            if hand_34[t] >= 4:
                continue
            hand_34[t] += 1
            improved = Shanten.calculate_shanten(hand_34) < base_shanten
            hand_34[t] -= 1
            if improved:
                accepting.append(t)
        return accepting

    def _rank_discards(self, hand_34: list[int], visible_34: list[int]) -> list[DiscardOption]:
        candidates = [t for t in range(34) if hand_34[t] > 0]
        options: list[DiscardOption] = []

        for c in candidates:
            hand_after = list(hand_34)
            hand_after[c] -= 1
            shanten_after = Shanten.calculate_shanten(hand_after)
            accepting = self._accepting_tiles(hand_after, shanten_after)
            live_total = 0
            for t in accepting:
                used = hand_after[t] + visible_34[t]
                live_total += max(0, 4 - used)
            options.append(
                DiscardOption(
                    tile=c,
                    shanten_after=shanten_after,
                    ukeire_tiles=accepting,
                    ukeire_kinds=len(accepting),
                    ukeire_live=live_total,
                )
            )

        def sort_key(opt: DiscardOption) -> tuple:
            visible_of_discard = visible_34[opt.tile]
            return (
                opt.shanten_after,
                -opt.ukeire_live,
                -opt.ukeire_kinds,
                -visible_of_discard,
            )

        options.sort(key=sort_key)
        return options
