"""Command line entry point: ``python -m card_stat_stamp slab.jpg --grade 10 --pop 176``."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from PIL import Image

from .stamp import StampStyle, add_stamp, format_stamp


def _parse_color(value: str) -> tuple[int, int, int]:
    named = {
        "white": (255, 255, 255),
        "black": (0, 0, 0),
        "red": (228, 30, 38),
        "yellow": (255, 194, 60),
        "blue": (0, 122, 255),
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="card_stat_stamp",
        description=(
            "Stamp a graded card's grade, population count and the date they "
            "were read onto its photo."
        ),
        epilog=(
            "The grade is the number on the slab label (beside GEM MT / NM-MT); "
            "the population is that grade's count on the grading-distribution screen."
        ),
    )
    parser.add_argument("image", type=Path, help="photo of the slab")
    parser.add_argument("--grade", help="grade from the slab label, e.g. 10")
    parser.add_argument("--pop", help="population for that grade, e.g. 176")
    parser.add_argument(
        "--date",
        help="date the population was read, YYYY-MM-DD or YYYY/MM/DD (default: today)",
    )
    parser.add_argument(
        "--no-date", action="store_true", dest="no_date", help="leave the date line off"
    )
    parser.add_argument(
        "-o", "--output", type=Path, help="output file (default: <input>_stamped.jpg)"
    )
    parser.add_argument("--font", help="path to the font to draw with")
    parser.add_argument(
        "--fill", type=_parse_color, default=(255, 255, 255), help="text colour"
    )
    parser.add_argument(
        "--outline", type=_parse_color, default=(228, 30, 38), help="outline colour"
    )
    parser.add_argument(
        "--block-top",
        type=float,
        dest="block_top",
        help="top of the grade line, as a fraction of the photo height (default: 0.600)",
    )
    parser.add_argument(
        "--date-top",
        type=float,
        dest="date_top",
        help="top of the date line, as a fraction of the photo height (default: 0.880)",
    )
    parser.add_argument(
        "--quality", type=int, default=95, help="JPEG quality of the output (default: 95)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        image = Image.open(args.image)
    except OSError as exc:
        print(f"error: cannot open {args.image}: {exc}", file=sys.stderr)
        return 1

    when = None if args.no_date else (args.date or date.today())
    text = format_stamp(grade=args.grade, pop=args.pop, when=when)

    style = StampStyle(fill=args.fill, outline=args.outline)
    if args.block_top is not None:
        style.block_top = args.block_top
    if args.date_top is not None:
        style.date_top = args.date_top

    try:
        result = add_stamp(image, text, style=style, font=args.font)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output = args.output or args.image.with_name(f"{args.image.stem}_stamped.jpg")
    if output.suffix.lower() in {".jpg", ".jpeg"}:
        result.save(output, quality=args.quality, subsampling=0)
    else:
        result.save(output)
    print(
        f"{text.grade or '-'} / {text.pop or '-'} / {text.date or '-'} -> {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
