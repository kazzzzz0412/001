"""Command line entry point: ``python -m card_title_overlay photo.jpg "タイトル"``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

from .overlay import (
    TitleLines,
    TitleStyle,
    add_title,
    find_artwork_band,
    find_card_band,
    find_font,
)


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


def _parse_band(value: str) -> tuple[int, int]:
    try:
        y0, y1 = (int(part) for part in value.split(":", 1))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--band expects Y0:Y1") from exc
    if y1 <= y0:
        raise argparse.ArgumentTypeError("--band expects Y0:Y1 with Y1 greater than Y0")
    return y0, y1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="card_title_overlay",
        description=(
            "Draw a listing title on a photo of cards - heavy white gothic text "
            "in a red outline, kept clear of the card artwork."
        ),
    )
    parser.add_argument("image", type=Path, help="photo to caption")
    parser.add_argument(
        "title",
        nargs="?",
        default="",
        help='the title, e.g. "希少 カイリキー 進化系 eカード 3連番 セット"',
    )
    parser.add_argument("-o", "--output", type=Path, help="output file (default: <input>_title.jpg)")
    parser.add_argument("--top", help="override the small line above the main one")
    parser.add_argument("--main", help="override the big line")
    parser.add_argument("--bottom", help="override the line under the cards")
    parser.add_argument("--font", help="path to the font to draw with")
    parser.add_argument(
        "--fill", type=_parse_color, default=(255, 255, 255), help="text colour (default: white)"
    )
    parser.add_argument(
        "--outline", type=_parse_color, default=(228, 30, 38), help="outline colour (default: red)"
    )
    parser.add_argument(
        "--weight",
        type=float,
        help="extra stroke on every glyph, as a fraction of the font size (default: 0.035)",
    )
    parser.add_argument(
        "--tracking",
        type=float,
        help="gap between characters, as a fraction of the font size (default: 0.05)",
    )
    parser.add_argument(
        "--bearing",
        type=float,
        help=(
            "how much of a font's own side margins to keep, 0 to 1 "
            "(default: 0.45; 0 spaces purely by ink, 1 by advance width)"
        ),
    )
    parser.add_argument(
        "--word-gap",
        type=float,
        dest="word_gap",
        help="gap where the title had a space, as a fraction of the font size (default: 0.34)",
    )
    parser.add_argument(
        "--protect",
        choices=("card", "art"),
        default="card",
        help=(
            "what the text must keep off: 'card' the whole card, label aside "
            "(default), or 'art' the illustrations only"
        ),
    )
    parser.add_argument(
        "--band",
        type=_parse_band,
        help="rows Y0:Y1 the artwork occupies, instead of detecting them",
    )
    parser.add_argument(
        "--quality", type=int, default=95, help="JPEG quality of the output (default: 95)"
    )
    parser.add_argument(
        "--show",
        action="store_true",
        dest="show_only",
        help="print the layout it would use and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        image = Image.open(args.image)
    except OSError as exc:
        print(f"error: cannot open {args.image}: {exc}", file=sys.stderr)
        return 1

    overrides = (args.top, args.main, args.bottom)
    if any(part is not None for part in overrides):
        title: str | TitleLines = TitleLines(
            top=args.top or "", main=args.main or "", bottom=args.bottom or ""
        )
    else:
        title = args.title

    if args.show_only:
        try:
            finder = find_card_band if args.protect == "card" else find_artwork_band
            band = args.band or finder(image)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        from .overlay import split_title

        lines = split_title(title) if isinstance(title, str) else title
        print(f"font: {find_font(args.font)}")
        print(f"artwork rows: {band[0]}-{band[1]} of {image.size[1]}")
        print(f"top:    {lines.top!r}")
        print(f"main:   {lines.main!r}")
        print(f"bottom: {lines.bottom!r}")
        return 0

    style = TitleStyle(fill=args.fill, outline=args.outline)
    if args.weight is not None:
        style.weight_ratio = args.weight
    if args.tracking is not None:
        style.tracking_ratio = args.tracking
    if args.bearing is not None:
        style.bearing_ratio = args.bearing
    if args.word_gap is not None:
        style.word_gap_ratio = args.word_gap
    try:
        result, lines, band = add_title(
            image, title, style=style, font=args.font, band=args.band, protect=args.protect
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output = args.output or args.image.with_name(f"{args.image.stem}_title.jpg")
    if output.suffix.lower() in {".jpg", ".jpeg"}:
        result.save(output, quality=args.quality, subsampling=0)
    else:
        result.save(output)
    print(
        f"artwork rows {band[0]}-{band[1]}; "
        f"top={lines.top!r} main={lines.main!r} bottom={lines.bottom!r} -> {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
