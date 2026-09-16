"""Interactive terminal REPL for the discard advisor.

This is the guaranteed-working core of the tool: no screen access, no
calibration, no GUI dependency. Type your hand each turn (mpsz notation,
e.g. ``123456789m123p1s9s``) and get an instant ranked discard suggestion;
feed in opponents' discards and riichi calls to turn on danger reading.
"""

from __future__ import annotations

from mahjong_advisor.session import HELP, AdvisorSession


def run_repl() -> None:
    session = AdvisorSession()

    print("麻雀打牌アドバイザー（効率＋危険牌読み・手入力モード）")
    print("'help' で使い方を表示します。")

    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if line.lower() in ("quit", "exit", "q"):
            break

        response = session.handle(line)
        if response:
            print(response)


if __name__ == "__main__":
    run_repl()
