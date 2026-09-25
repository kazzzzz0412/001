"""Command line entry point: ``python -m card_grade_marker screenshot.jpg``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

from .marker import MarkerStyle, detect_chip_row, highlight_grade
from .table import find_table, mark_table


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


def _parse_span(value: str, flag: str, axis: str) -> tuple[int, int]:
    try:
        low, high = (int(part) for part in value.split(":", 1))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{flag} expects {axis}0:{axis}1") from exc
    if high <= low:
        raise argparse.ArgumentTypeError(
            f"{flag} expects {axis}0:{axis}1 with {axis}1 greater than {axis}0"
        )
    return low, high


def _parse_band(value: str) -> tuple[int, int]:
    return _parse_span(value, "--band", "Y")


def _parse_pad(value: str) -> int | tuple[int, int]:
    parts = value.split(":")
    try:
        numbers = [int(part) for part in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--pad expects N or TOP:BOTTOM") from exc
    if len(numbers) == 1:
        return numbers[0]
    if len(numbers) == 2:
        return numbers[0], numbers[1]
    raise argparse.ArgumentTypeError("--pad expects N or TOP:BOTTOM")


def _parse_chip(value: str) -> tuple[int, int]:
    return _parse_span(value, "--chip", "X")


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
        "-r",
        "--row",
        type=int,
        help=(
            "for the table layout the app uses now: which grade row to keep, "
            "counted from the top (1-based, header and 合計 excluded)"
        ),
    )
    parser.add_argument(
        "--mark",
        choices=("ring", "arrow"),
        default="ring",
        help="how to mark the kept table row (default: a ring around it)",
    )
    parser.add_argument(
        "--band",
        type=_parse_band,
        help="force the chip row to rows Y0:Y1 instead of detecting it",
    )
    parser.add_argument(
        "--chip",
        type=_parse_chip,
        help=(
            "keep the columns X0:X1 instead of a detected chip, for when "
            "something overlapping a chip is read as part of it"
        ),
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
        "--pad",
        type=_parse_pad,
        help="extra rows erased above and below the chip row: N, or TOP:BOTTOM",
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
        if args.row is None:
            try:
                row = detect_chip_row(image, band=args.band)
            except ValueError:
                pass
            else:
                print(f"chip row: rows {row.y0}-{row.y1}, background rgb{row.background}")
                for i, chip in enumerate(row.chips, start=1):
                    mark = " <- selected" if chip.selected else ""
                    print(f"  {i}: x {chip.x0}-{chip.x1} (width {chip.width}){mark}")
                return 0
        try:
            table = find_table(image)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"table: x {table.x0}-{table.x1}, background rgb{table.background}")
        grade = 0
        for entry in table.rows:
            label = entry.kind
            if entry.kind == "grade":
                grade += 1
                label = f"grade row {grade}"
            print(f"  {label}: rows {entry.y0}-{entry.y1}")
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

    output = args.output or args.image.with_name(f"{args.image.stem}_marked.png")

    if args.row is not None:
        try:
            table = find_table(image)
            result = mark_table(image, table, args.row - 1, style, mark=args.mark)
        except (ValueError, IndexError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        result.save(output)
        kept = table.grades[args.row - 1]
        print(
            f"kept grade row {args.row} of {len(table.grades)} "
            f"(rows {kept.y0}-{kept.y1}) -> {output}"
        )
        return 0

    try:
        result, row, index = highlight_grade(
            image, target=target, style=style, band=args.band, chip=args.chip
        )
    except (ValueError, IndexError) as chips_failed:
        try:
            table = find_table(image)
        except ValueError:
            print(f"error: {chips_failed}", file=sys.stderr)
            return 1
        print(
            "error: this screenshot lays the grades out as a table; choose the "
            f"row with --row N (1..{len(table.grades)}, counted from the top)",
            file=sys.stderr,
        )
        return 1

    result.save(output)
    chip = row.chips[index]
    print(
        f"kept chip {index + 1} of {len(row.chips)} (x {chip.x0}-{chip.x1}, "
        f"rows {row.y0}-{row.y1}) -> {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
