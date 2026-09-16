"""Interactive terminal REPL for the discard advisor.

This is the guaranteed-working core of the tool: no screen access, no
calibration, no GUI dependency. Type your hand each turn (mpsz notation,
e.g. ``123456789m123p1s9s``) and get an instant ranked discard suggestion.
"""

from __future__ import annotations

from mahjong.tile import TilesConverter

from mahjong_advisor.engine.advisor import Advisor
from mahjong_advisor.formatting import format_analysis

HELP = """\
使い方:
  手札をmpsz記法で入力してEnter。例: 123456789m123p1s9s (13枚か14枚)
  v <tiles>   見えている牌（他人の捨て牌やドラ表示牌など）を追加して残り枚数の精度を上げる
              例: v 1s1s1s5p
  reset       見えている牌の記録をリセット（新しい局の開始時に）
  help        このヘルプを表示
  quit / exit 終了
"""


def _parse_tiles(text: str) -> list[int]:
    return TilesConverter.one_line_string_to_34_array(text, has_aka_dora=True)


def run_repl() -> None:
    advisor = Advisor()
    visible = [0] * 34

    print("麻雀打牌アドバイザー（効率重視・手入力モード）")
    print("'help' で使い方を表示します。")

    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue
        if line in ("quit", "exit", "q"):
            break
        if line in ("help", "h", "?"):
            print(HELP)
            continue
        if line == "reset":
            visible = [0] * 34
            print("見えている牌の記録をリセットしました。")
            continue
        if line.startswith("v ") or line.startswith("see "):
            tiles_str = line.split(" ", 1)[1].strip()
            try:
                added = _parse_tiles(tiles_str)
            except Exception as exc:  # noqa: BLE001 - surface parse errors to the user
                print(f"解析エラー: {exc}")
                continue
            for i in range(34):
                visible[i] += added[i]
            print("追加しました。")
            continue

        try:
            result = advisor.analyze(line, visible=visible)
        except Exception as exc:  # noqa: BLE001 - surface parse/validation errors
            print(f"エラー: {exc}")
            continue

        print(format_analysis(result))


if __name__ == "__main__":
    run_repl()
