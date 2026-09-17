"""Sticker records and the normalization that turns handwriting into cell values.

A handwritten inventory sticker is read as free text - "R6.3.5", "￥1,200-",
"美品" - and a spreadsheet wants "2024/03/05", 1200, "A". Normalization lives
here, separate from the model call, so every table below is testable without
touching the API.

Every value carries the confidence the reader reported for it. Normalizing can
*lower* that confidence (an inferred year is a guess, not a reading), which is
what later flags a cell for human review.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date

FIELD_NAMES = ("management_no", "purchased_on", "price", "condition")
"""The four things a sticker carries, in the order they are reported."""

JAPANESE_ERAS = {
    "R": 2018,  # 令和1年 = 2019, so year N is 2018 + N
    "H": 1988,  # 平成31年 = 2019
    "S": 1925,  # 昭和64年 = 1989
}

_ERA_ALIASES = {"令和": "R", "平成": "H", "昭和": "S"}

_INFERRED_YEAR_CONFIDENCE = 0.4
"""A sticker that only says "3/5" tells us nothing about the year. We fill in a
plausible one so the cell is usable, but cap the confidence so it gets flagged."""


@dataclass
class FieldValue:
    """One cell's worth of reading: what it becomes, and how sure we are."""

    value: str = ""
    confidence: float = 0.0
    raw: str = ""
    note: str = ""

    @property
    def is_blank(self) -> bool:
        return not str(self.value).strip()


@dataclass
class StickerRecord:
    management_no: FieldValue = field(default_factory=FieldValue)
    purchased_on: FieldValue = field(default_factory=FieldValue)
    price: FieldValue = field(default_factory=FieldValue)
    condition: FieldValue = field(default_factory=FieldValue)
    source_image: str = ""

    def fields(self) -> dict[str, FieldValue]:
        return {name: getattr(self, name) for name in FIELD_NAMES}

    @property
    def key(self) -> str:
        return self.management_no.value


def normalize_text(text: str) -> str:
    """NFKC-fold so full-width digits, ･ and ￥ compare as their ASCII forms."""
    return unicodedata.normalize("NFKC", str(text or "")).strip()


def normalize_management_no(raw: str) -> str:
    """Management numbers are written with stray spaces and full-width digits."""
    return re.sub(r"\s+", "", normalize_text(raw)).upper()


_PRICE_JUNK = re.compile(r"[^\d.]")


def parse_price(raw: str) -> int | None:
    """Read a handwritten price: "￥1,200-", "1200円", "１２００" all mean 1200.

    A trailing "-" (the bookkeeping dash for "and no sen") is junk, not a minus
    sign, and prices on a sticker are never negative - so strip it with the rest
    rather than parsing a sign.
    """
    text = normalize_text(raw)
    if not text:
        return None
    digits = _PRICE_JUNK.sub("", text)
    if not digits:
        return None
    try:
        return int(round(float(digits)))
    except ValueError:
        return None


_DATE_SEPARATORS = re.compile(r"[/\.\-年月日\s]+")


def parse_date(raw: str, *, today: date | None = None) -> tuple[date | None, bool]:
    """Read a handwritten date. Returns (date, year_was_inferred).

    Handles western years (2024/3/5, 24.3.5), Japanese eras (R6.3.5, 令和6年3月5日)
    and the very common year-less sticker (3/5), where the year is inferred as
    the most recent one that has not passed yet.
    """
    today = today or date.today()
    text = normalize_text(raw)
    if not text:
        return None, False

    era_offset: int | None = None
    for word, letter in _ERA_ALIASES.items():
        if text.startswith(word):
            text = text[len(word) :]
            era_offset = JAPANESE_ERAS[letter]
            break
    else:
        if text[:1].upper() in JAPANESE_ERAS and not text[:1].isdigit():
            era_offset = JAPANESE_ERAS[text[:1].upper()]
            text = text[1:]

    parts = [p for p in _DATE_SEPARATORS.split(text) if p]
    if not all(p.isdigit() for p in parts):
        return None, False

    numbers = [int(p) for p in parts]
    inferred_year = False

    if len(numbers) >= 3:
        year, month, day = numbers[0], numbers[1], numbers[2]
        if era_offset is not None:
            year += era_offset
        elif year < 100:
            # A 2-digit year on an inventory sticker is this century.
            year += 2000
    elif len(numbers) == 2:
        month, day = numbers
        year = today.year
        inferred_year = True
    else:
        return None, False

    try:
        parsed = date(year, month, day)
    except ValueError:
        return None, False

    if inferred_year and parsed > today:
        # "12/28" written in January means last December, not next December.
        try:
            parsed = parsed.replace(year=year - 1)
        except ValueError:  # 2/29 in a non-leap year
            return None, False

    return parsed, inferred_year


def normalize_condition(raw: str, aliases: dict[str, str] | None = None) -> str:
    """Map a written condition onto the vocabulary the sheet already uses."""
    text = normalize_text(raw)
    if not text:
        return ""
    table = {normalize_text(k): v for k, v in (aliases or {}).items()}
    return table.get(text, text)


def normalize_record(
    record: StickerRecord,
    *,
    date_format: str = "%Y/%m/%d",
    condition_aliases: dict[str, str] | None = None,
    today: date | None = None,
) -> StickerRecord:
    """Turn one raw reading into the exact strings that go into cells."""
    management_no = replace(
        record.management_no, value=normalize_management_no(record.management_no.value)
    )

    parsed, inferred = parse_date(record.purchased_on.value, today=today)
    if parsed is None:
        purchased_on = replace(
            record.purchased_on,
            value="",
            confidence=0.0,
            note="日付を読み取れませんでした" if record.purchased_on.value else "",
        )
    else:
        purchased_on = replace(
            record.purchased_on,
            value=parsed.strftime(date_format),
            confidence=min(record.purchased_on.confidence, _INFERRED_YEAR_CONFIDENCE)
            if inferred
            else record.purchased_on.confidence,
            note="年の記載がないため推定しました" if inferred else "",
        )

    amount = parse_price(record.price.value)
    price = replace(
        record.price,
        value="" if amount is None else str(amount),
        confidence=0.0 if amount is None else record.price.confidence,
        note="価格を読み取れませんでした" if amount is None and record.price.value else "",
    )

    condition = replace(
        record.condition, value=normalize_condition(record.condition.value, condition_aliases)
    )

    return StickerRecord(
        management_no=management_no,
        purchased_on=purchased_on,
        price=price,
        condition=condition,
        source_image=record.source_image,
    )


def to_dicts(records: list[StickerRecord]) -> list[dict]:
    """Serialize a read so it can be re-planned without paying for it twice."""
    return [
        {
            "source_image": record.source_image,
            **{
                name: {"value": value.value, "confidence": value.confidence, "note": value.note}
                for name, value in record.fields().items()
            },
        }
        for record in records
    ]


def from_dicts(payload: list[dict]) -> list[StickerRecord]:
    records = []
    for item in payload:
        values = {}
        for name in FIELD_NAMES:
            raw = item.get(name) or {}
            values[name] = FieldValue(
                value=str(raw.get("value", "")),
                confidence=float(raw.get("confidence", 0.0) or 0.0),
                raw=str(raw.get("value", "")),
                note=str(raw.get("note", "")),
            )
        records.append(StickerRecord(source_image=item.get("source_image", ""), **values))
    return records
