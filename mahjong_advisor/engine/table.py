"""Table state: who discarded what, who is threatening, what is still unseen.

The danger model needs more than a flat "visible tiles" pool - it needs to know
*which* opponent discarded a tile (that tile is furiten-safe against them, and
only them) and when a riichi was declared (every tile discarded by anyone after
that point has passed the riichi player, so it is safe against them too).
"""

from __future__ import annotations

from dataclasses import dataclass, field

ME = 0
"""Player index of the user in the discard timeline."""

DEFAULT_OPPONENT_LABELS = ("下家", "対面", "上家")

THREAT_RIICHI = 1.0
THREAT_SUSPECTED = 0.5
"""Melded / damaten-suspected opponent: treated as half as likely to be tenpai."""


@dataclass
class Opponent:
    label: str
    discards: list[int] = field(default_factory=list)
    riichi_timeline_index: int | None = None
    """Position in the global timeline when this opponent declared riichi."""
    suspected: bool = False
    """Marked by the user as melded / looking tenpai (damaten)."""

    @property
    def is_riichi(self) -> bool:
        return self.riichi_timeline_index is not None

    @property
    def threat(self) -> float:
        if self.is_riichi:
            return THREAT_RIICHI
        if self.suspected:
            return THREAT_SUSPECTED
        return 0.0

    @property
    def threat_label(self) -> str:
        if self.is_riichi:
            return "リーチ"
        if self.suspected:
            return "警戒"
        return "-"


@dataclass
class TableState:
    opponents: list[Opponent] = field(
        default_factory=lambda: [Opponent(label) for label in DEFAULT_OPPONENT_LABELS]
    )
    timeline: list[tuple[int, int]] = field(default_factory=list)
    """Every discard so far as (player_index, tile_34), in order. Player 0 is me."""
    my_discards: list[int] = field(default_factory=list)
    dora_indicators: list[int] = field(default_factory=list)
    extra_visible: list[int] = field(default_factory=lambda: [0] * 34)
    """Anything else you can see (opponents' melds, etc.) as a 34-count array."""
    turn: int = 1

    # -- mutation ----------------------------------------------------------
    def discard(self, player: int, tile: int) -> None:
        """Record a discard. player 0 = me, 1..3 = 下家/対面/上家."""
        if not 0 <= player <= 3:
            raise ValueError(f"player must be 0..3, got {player}")
        self.timeline.append((player, tile))
        if player == ME:
            self.my_discards.append(tile)
        else:
            self.opponents[player - 1].discards.append(tile)

    def declare_riichi(self, player: int) -> None:
        if not 1 <= player <= 3:
            raise ValueError(f"riichi player must be 1..3, got {player}")
        opponent = self.opponents[player - 1]
        # Tiles that pass from here on are safe against this opponent.
        opponent.riichi_timeline_index = len(self.timeline)

    def mark_suspected(self, player: int, suspected: bool = True) -> None:
        if not 1 <= player <= 3:
            raise ValueError(f"player must be 1..3, got {player}")
        self.opponents[player - 1].suspected = suspected

    def add_visible(self, counts_34: list[int]) -> None:
        for i in range(34):
            self.extra_visible[i] += counts_34[i]

    def reset(self) -> None:
        self.opponents = [Opponent(label) for label in DEFAULT_OPPONENT_LABELS]
        self.timeline = []
        self.my_discards = []
        self.dora_indicators = []
        self.extra_visible = [0] * 34
        self.turn = 1

    # -- derived views -----------------------------------------------------
    def safe_tiles(self, opponent: Opponent) -> set[int]:
        """Tiles this opponent cannot ron: their own discards, plus (after a
        riichi) everything that has passed since they declared."""
        safe = set(opponent.discards)
        if opponent.riichi_timeline_index is not None:
            safe |= {tile for _player, tile in self.timeline[opponent.riichi_timeline_index :]}
        return safe

    def board_visible_34(self) -> list[int]:
        """Everything visible on the table, excluding the tiles in my hand."""
        counts = list(self.extra_visible)
        for _player, tile in self.timeline:
            counts[tile] += 1
        for tile in self.dora_indicators:
            counts[tile] += 1
        return counts

    def unseen_34(self, hand_34: list[int]) -> list[int]:
        """Copies of each tile that could still be in the wall or an opponent's
        hand - i.e. not on the table and not in my own hand."""
        board = self.board_visible_34()
        return [max(0, 4 - board[i] - hand_34[i]) for i in range(34)]

    def threatening_opponents(self) -> list[Opponent]:
        return [opponent for opponent in self.opponents if opponent.threat > 0]

    @property
    def has_threat(self) -> bool:
        return bool(self.threatening_opponents())
