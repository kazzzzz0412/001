"""Shared command layer driving one table's state.

The CLI and the overlay both feed single lines of text in here and print what
comes back, so opponent tracking, riichi flags and stance behave identically in
both front-ends.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mahjong_advisor.engine.advisor import STANCE_AUTO, STANCE_FOLD, STANCE_PUSH, Advisor
from mahjong_advisor.engine.names import tile_notation
from mahjong_advisor.engine.table import TableState
from mahjong_advisor.formatting import format_analysis

SUIT_BASE = {"m": 0, "p": 9, "s": 18, "z": 27}

HELP = """\
手牌を入力:
  123456789m123p1s9s   mpsz記法で13枚/14枚。すぐに「切るならこれ」を表示
場況を入力（危険牌読みが有効になります）:
  d1 5p / d2 3s1z      下家(1)/対面(2)/上家(3) が切った牌を記録（複数可）
  d 5p 3s 1z           1周分をまとめて記録（下家→対面→上家の順）
  d0 5m                自分が切った牌を記録
  r2                   対面がリーチ（以降に通った牌も安全牌として扱います）
  w2 / w2 off          対面を警戒（鳴き・ダマ気配）/ 解除
  t 9                  巡目を設定（押し引き判断に使用）
  dora 3m              ドラ表示牌を追加
  v 5p5p               その他の見えている牌（他家の副露など）を追加
打ち方の指定:
  auto / push / fold   自動判断（既定）/ 押し優先 / ベタオリ優先
その他:
  state                現在の場況を表示
  reset                新しい局として全部リセット
  help / quit
"""


def parse_tiles_ordered(text: str) -> list[int]:
    """'3s1z' -> [20, 27], preserving input order. '0' means a red five."""
    tiles: list[int] = []
    pending: list[str] = []
    for char in text.replace(" ", ""):
        if char.isdigit():
            pending.append(char)
        elif char in SUIT_BASE:
            for digit in pending:
                rank = int(digit)
                if char == "z":
                    if not 1 <= rank <= 7:
                        raise ValueError(f"字牌は1z-7zです: {rank}z")
                else:
                    if rank == 0:
                        rank = 5  # red five
                    if not 1 <= rank <= 9:
                        raise ValueError(f"数牌は1-9です: {rank}{char}")
                tiles.append(SUIT_BASE[char] + rank - 1)
            pending = []
        else:
            raise ValueError(f"解釈できない文字です: {char}")
    if pending:
        raise ValueError(f"牌の種類(m/p/s/z)がありません: {''.join(pending)}")
    return tiles


@dataclass
class AdvisorSession:
    advisor: Advisor = field(default_factory=Advisor)
    table: TableState = field(default_factory=TableState)
    stance: str = STANCE_AUTO

    def handle(self, line: str) -> str:
        line = line.strip()
        if not line:
            return ""

        command, _, rest = line.partition(" ")
        command = command.lower()
        rest = rest.strip()

        try:
            return self._dispatch(command, rest, line)
        except ValueError as exc:
            return f"エラー: {exc}"

    # -- dispatch ----------------------------------------------------------
    def _dispatch(self, command: str, rest: str, line: str) -> str:
        if command in ("help", "h", "?"):
            return HELP
        if command == "state":
            return self.describe_state()
        if command == "reset":
            self.table.reset()
            self.stance = STANCE_AUTO
            return "場況をリセットしました。"
        if command in (STANCE_AUTO, STANCE_PUSH, STANCE_FOLD):
            self.stance = command
            labels = {STANCE_AUTO: "自動判断", STANCE_PUSH: "押し優先", STANCE_FOLD: "ベタオリ優先"}
            return f"打ち方: {labels[command]}"
        if command == "t":
            return self._set_turn(rest)
        if command == "dora":
            return self._add_dora(rest)
        if command in ("v", "see"):
            return self._add_visible(rest)
        if command == "d":
            return self._discard_round(rest)
        if command.startswith("d") and command[1:].isdigit():
            return self._discard_for(int(command[1:]), rest)
        if command.startswith("r") and command[1:].isdigit():
            return self._riichi(int(command[1:]))
        if command == "r":
            return self._riichi(int(rest)) if rest.isdigit() else "エラー: r2 のように指定してください。"
        if command.startswith("w") and command[1:].isdigit():
            return self._suspect(int(command[1:]), rest)

        return self._analyze(line)

    # -- commands ----------------------------------------------------------
    def _set_turn(self, rest: str) -> str:
        if not rest.isdigit():
            raise ValueError("巡目は数字で指定してください（例: t 9）。")
        self.table.turn = max(1, min(18, int(rest)))
        return f"{self.table.turn}巡目に設定しました。"

    def _add_dora(self, rest: str) -> str:
        tiles = parse_tiles_ordered(rest)
        if not tiles:
            raise ValueError("ドラ表示牌を指定してください（例: dora 3m）。")
        self.table.dora_indicators.extend(tiles)
        shown = "/".join(tile_notation(t) for t in tiles)
        return f"ドラ表示牌を追加: {shown}"

    def _add_visible(self, rest: str) -> str:
        tiles = parse_tiles_ordered(rest)
        if not tiles:
            raise ValueError("牌を指定してください（例: v 5p5p）。")
        counts = [0] * 34
        for tile in tiles:
            counts[tile] += 1
        self.table.add_visible(counts)
        return f"見えている牌を追加: {'/'.join(tile_notation(t) for t in tiles)}"

    def _discard_for(self, player: int, rest: str) -> str:
        if not 0 <= player <= 3:
            raise ValueError("プレイヤーは d0(自分) / d1(下家) / d2(対面) / d3(上家) です。")
        tiles = parse_tiles_ordered(rest)
        if not tiles:
            raise ValueError("牌を指定してください（例: d2 3s）。")
        for tile in tiles:
            self.table.discard(player, tile)
        who = "自分" if player == 0 else self.table.opponents[player - 1].label
        return f"{who}の捨て牌に追加: {'/'.join(tile_notation(t) for t in tiles)}"

    def _discard_round(self, rest: str) -> str:
        """`d 5p 3s 1z` - one tile each for 下家/対面/上家, in turn order."""
        groups = rest.split()
        if not groups:
            raise ValueError("例: d 5p 3s 1z （下家→対面→上家の順）")
        if len(groups) > 3:
            raise ValueError("d では最大3人分まで指定できます。")
        recorded = []
        for offset, group in enumerate(groups):
            for tile in parse_tiles_ordered(group):
                self.table.discard(offset + 1, tile)
                recorded.append(f"{self.table.opponents[offset].label}:{tile_notation(tile)}")
        return "捨て牌を記録: " + " ".join(recorded)

    def _riichi(self, player: int) -> str:
        if not 1 <= player <= 3:
            raise ValueError("リーチは r1(下家) / r2(対面) / r3(上家) で指定してください。")
        self.table.declare_riichi(player)
        label = self.table.opponents[player - 1].label
        return f"{label}のリーチを記録しました。以降に場に通った牌は安全牌として扱います。"

    def _suspect(self, player: int, rest: str) -> str:
        if not 1 <= player <= 3:
            raise ValueError("警戒は w1 / w2 / w3 で指定してください。")
        off = rest.lower() in ("off", "no", "解除")
        self.table.mark_suspected(player, not off)
        label = self.table.opponents[player - 1].label
        return f"{label}の警戒を{'解除' if off else '設定'}しました。"

    def _analyze(self, hand: str) -> str:
        tiles = parse_tiles_ordered(hand)
        if len(tiles) not in (13, 14):
            raise ValueError(
                f"手牌は13枚か14枚で入力してください（{len(tiles)}枚）。コマンド一覧は 'help'。"
            )
        counts = [0] * 34
        for tile in tiles:
            counts[tile] += 1
        result = self.advisor.analyze(counts, table=self.table, stance=self.stance)
        return format_analysis(result)

    # -- display -----------------------------------------------------------
    def describe_state(self) -> str:
        lines = [f"{self.table.turn}巡目 / 打ち方: {self.stance}"]
        if self.table.dora_indicators:
            lines.append("ドラ表示: " + "/".join(tile_notation(t) for t in self.table.dora_indicators))
        for opponent in self.table.opponents:
            discards = "/".join(tile_notation(t) for t in opponent.discards) or "なし"
            lines.append(f"  {opponent.label} [{opponent.threat_label}] {discards}")
        return "\n".join(lines)
