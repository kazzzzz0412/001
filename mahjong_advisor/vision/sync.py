"""Fold a freshly-read discard pile into the table state.

Reading the screen gives the pile as it looks *now*; the table state holds the
history we have already recorded. Two things make this more than a length
comparison:

* When someone calls pon/chi, the called tile leaves the discard pile, so the
  pile on screen is a *subsequence* of what was actually discarded.
* A called tile still counts as discarded for our purposes - furiten and
  "passed after the riichi" both depend on the discard having happened, not on
  the tile still sitting in the pile.

So this only ever appends. Recorded tiles are never removed because they
vanished from the screen, and tiles are aligned as a subsequence so a call in
the middle of the pile does not make every later tile look new.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mahjong_advisor.engine.names import tile_notation
from mahjong_advisor.engine.table import TableState


@dataclass
class PileSync:
    player: int
    added: list[int] = field(default_factory=list)
    suspicious: bool = False
    """True when the read looks wrong rather than merely new (see below)."""

    @property
    def added_notation(self) -> list[str]:
        return [tile_notation(tile) for tile in self.added]


MAX_PLAUSIBLE_NEW_TILES = 6
"""More new tiles than this in one read means tiles were missed or misread,
not that the opponent discarded that many since you last looked."""


def diff_pile(known: list[int], observed: list[int]) -> list[int]:
    """Tiles in `observed` that are not accounted for by `known`.

    `observed` is matched against `known` as a subsequence, so tiles missing
    from the middle (called by someone) do not shift everything after them into
    looking new.
    """
    cursor = 0
    new: list[int] = []
    for tile in observed:
        try:
            cursor = known.index(tile, cursor) + 1
        except ValueError:
            new.append(tile)
    return new


def sync_pile(table: TableState, player: int, observed: list[int]) -> PileSync:
    """Record whatever `observed` shows that the table state does not have yet."""
    if not 1 <= player <= 3:
        raise ValueError(f"player must be 1..3, got {player}")

    known = table.opponents[player - 1].discards
    new_tiles = diff_pile(known, observed)

    result = PileSync(player=player, added=list(new_tiles))
    if len(new_tiles) > MAX_PLAUSIBLE_NEW_TILES:
        # Don't poison the table state with a bad read - report and skip.
        result.suspicious = True
        result.added = []
        return result

    for tile in new_tiles:
        table.discard(player, tile)
    return result


def describe_syncs(syncs: list[PileSync], table: TableState) -> str:
    """One line summarising what a screen read added, for the user to eyeball."""
    parts = []
    for sync in syncs:
        label = table.opponents[sync.player - 1].label
        if sync.suspicious:
            parts.append(f"{label}:読み取り怪しい(スキップ)")
        elif sync.added:
            parts.append(f"{label}:+{'/'.join(sync.added_notation)}")
    return " ".join(parts) if parts else "捨て牌の更新なし"
