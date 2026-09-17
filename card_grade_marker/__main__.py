"""Command line entry point: ``python -m card_grade_marker screenshot.jpg``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

from .marker import MarkerStyle, detect_chip_row, highlight_grade


def _parse_color(value: str) -> tuple[int, int, int]:
    named = {
        "black": (0, 0, 0),
        "white": (255, 255, 255),
        "yellow": (255, 194, 60),
        "red": (255, 69, 58),
        "green": (48, 209, 88),
    }
    key = value.strip().lower()
    if key in named:
        return named[key]
    text = key.lstrip("#")
    if len(text) != 6:
        raise argparse.ArgumentTypeError(f"unrecognised colour: {value}")
    try:
        return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError as exc:  # pragma: no cover - argparse reports it
        raise argparse.ArgumentTypeError(f"unrecognised colour: {value}") from exc


def _parse_band(value: str) -> tuple[int, int]:
    try:
        y0, y1 = (int(part) for part in value.split(":", 1))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--band expects Y0:Y1, e.g. 1654:1875") from exc
    if y1 <= y0:
        raise argparse.ArgumentTypeError("--band expects Y0:Y1 with Y1 greater than Y0")
    return y0, y1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="card_grade_marker",
        description=(
            "Black out every grade chip except one and point a large arrow at "
            "the one that is left."
        ),
    )
    parser.add_argument("image", type=Path, help="screenshot to process")
    parser.add_argument(
        "-o", "--output", type=Path, help="output file (default: <input>_marked.png)"
    )
    parser.add_argument(
        "-t",
        "--target",
        default="auto",
        help=(
            "which chip to keep: 'auto' for the one the app has selected "
            "(white border), or a 1-based position counted from the left"
        ),
    )
    parser.add_argument(
        "--band",
        type=_parse_band,
        help="force the chip row to rows Y0:Y1 instead of detecting it",
    )
    parser.add_argument(
        "--side",
        choices=("auto", "left", "right"),
        default="auto",
        help="which side of the chip the arrow sits on (default: the roomier one)",
    )
    parser.add_argument(
        "--color",
        type=_parse_color,
        default=(255, 194, 60),
        help="arrow colour, a name or #RRGGBB (default: amber)",
    )
    parser.add_argument(
        "--fill",
        default="bg",
        help="colour used to erase the other chips: 'bg' to match the page, or a colour",
    )
    parser.add_argument(
        "--pad", type=int, help="extra rows erased above and below the chip row"
    )
    parser.add_argument(
        "--ring", action="store_true", help="also draw a ring around the kept chip"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="print the detected chips and exit without writing an image",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        image = Image.open(args.image)
    except OSError as exc:
        print(f"error: cannot open {args.image}: {exc}", file=sys.stderr)
        return 1

    if args.list_only:
        try:
            row = detect_chip_row(image, band=args.band)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"chip row: rows {row.y0}-{row.y1}, background rgb{row.background}")
        for i, chip in enumerate(row.chips, start=1):
            mark = " <- selected" if chip.selected else ""
            print(f"  {i}: x {chip.x0}-{chip.x1} (width {chip.width}){mark}")
        return 0

    if str(args.target).lower() == "auto":
        target = None
    else:
        try:
            target = int(args.target) - 1
        except ValueError:
            print("error: --target expects 'auto' or a 1-based position", file=sys.stderr)
            return 1
        if target < 0:
            print("error: --target positions start at 1", file=sys.stderr)
            return 1

    style = MarkerStyle(
        arrow_color=args.color,
        fill_color=None if args.fill == "bg" else _parse_color(args.fill),
        side=args.side,
        ring=args.ring,
        pad=args.pad,
    )

    try:
        result, row, index = highlight_grade(image, target=target, style=style, band=args.band)
    except (ValueError, IndexError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output = args.output or args.image.with_name(f"{args.image.stem}_marked.png")
    result.save(output)
    chip = row.chips[index]
    print(
        f"kept chip {index + 1} of {len(row.chips)} (x {chip.x0}-{chip.x1}, "
        f"rows {row.y0}-{row.y1}) -> {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
