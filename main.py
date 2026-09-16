"""Entry point for the mahjong discard advisor.

  python main.py              manual hand-input REPL (no setup required)
  python main.py overlay      always-on-top overlay with a global hotkey
  python main.py calibrate    [experimental] set up screen-vision templates
  python main.py vision       [experimental] read hand + discard piles once
  python main.py vision --watch   same, re-triggered by a global hotkey
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Mahjong discard advisor (efficiency assistant, no autoplay)")
    sub = parser.add_subparsers(dest="mode")

    sub.add_parser("cli", help="manual hand-input REPL (default)")
    sub.add_parser("overlay", help="always-on-top overlay with a global hotkey")
    sub.add_parser("calibrate", help="[experimental] set up screen-vision regions + tile templates")
    vision_parser = sub.add_parser(
        "vision", help="[experimental] read your hand and the discard piles from the screen"
    )
    vision_parser.add_argument(
        "--watch", action="store_true", help="stay running and re-capture on a hotkey instead of once"
    )

    args = parser.parse_args()
    mode = args.mode or "cli"

    if mode == "cli":
        from mahjong_advisor.cli import run_repl

        run_repl()
    elif mode == "overlay":
        from mahjong_advisor.ui.overlay import OverlayApp

        OverlayApp().run()
    elif mode == "calibrate":
        from mahjong_advisor.vision.calibrate import run_calibration

        run_calibration()
    elif mode == "vision":
        from mahjong_advisor.vision.runner import run_vision_once, run_vision_watch

        if args.watch:
            run_vision_watch()
        else:
            run_vision_once()


if __name__ == "__main__":
    main()
