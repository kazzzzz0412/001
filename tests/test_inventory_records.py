from datetime import date

from inventory_filler.records import (
    FieldValue,
    StickerRecord,
    from_dicts,
    normalize_condition,
    normalize_management_no,
    normalize_record,
    parse_date,
    parse_price,
    to_dicts,
)


def test_parse_price_strips_currency_commas_and_bookkeeping_dash():
    assert parse_price("￥1,200-") == 1200
    assert parse_price("1200円") == 1200
    assert parse_price("１２００") == 1200
    assert parse_price("3,980") == 3980


def test_parse_price_returns_none_when_nothing_numeric():
    assert parse_price("") is None
    assert parse_price("不明") is None


def test_parse_date_western_forms():
    assert parse_date("2024/3/5") == (date(2024, 3, 5), False)
    assert parse_date("2024-03-05") == (date(2024, 3, 5), False)
    assert parse_date("24.3.5") == (date(2024, 3, 5), False)


def test_parse_date_japanese_eras():
    assert parse_date("R6.3.5") == (date(2024, 3, 5), False)
    assert parse_date("令和6年3月5日") == (date(2024, 3, 5), False)
    assert parse_date("H31/4/1") == (date(2019, 4, 1), False)


def test_parse_date_without_a_year_is_inferred_and_marked():
    parsed, inferred = parse_date("3/5", today=date(2024, 6, 1))
    assert (parsed, inferred) == (date(2024, 3, 5), True)


def test_parse_date_without_a_year_rolls_back_when_it_would_be_in_the_future():
    # "12/28" written in January is last December, not next December.
    parsed, inferred = parse_date("12/28", today=date(2024, 1, 10))
    assert (parsed, inferred) == (date(2023, 12, 28), True)


def test_parse_date_rejects_nonsense():
    assert parse_date("だいたい春頃") == (None, False)
    assert parse_date("2024/13/40") == (None, False)


def test_normalize_management_no_folds_width_and_drops_spaces():
    assert normalize_management_no("ａ- １２３ ") == "A-123"


def test_normalize_condition_uses_the_sheets_own_vocabulary():
    assert normalize_condition("美品", {"美品": "A"}) == "A"
    assert normalize_condition("難あり", {"美品": "A"}) == "難あり"


def _record(**kwargs):
    fields = {
        name: FieldValue(value=value, confidence=1.0, raw=value)
        for name, value in kwargs.items()
    }
    return StickerRecord(**fields)


def test_normalize_record_formats_every_field():
    normalized = normalize_record(
        _record(management_no="a-1", purchased_on="R6.3.5", price="￥1,200-", condition="美品"),
        date_format="%Y/%m/%d",
        condition_aliases={"美品": "A"},
    )
    assert normalized.management_no.value == "A-1"
    assert normalized.purchased_on.value == "2024/03/05"
    assert normalized.price.value == "1200"
    assert normalized.condition.value == "A"


def test_normalize_record_caps_confidence_on_an_inferred_year():
    normalized = normalize_record(
        _record(management_no="A-1", purchased_on="3/5", price="100", condition="A"),
        today=date(2024, 6, 1),
    )
    assert normalized.purchased_on.confidence <= 0.4
    assert "推定" in normalized.purchased_on.note


def test_normalize_record_zeroes_confidence_on_an_unreadable_price():
    normalized = normalize_record(_record(management_no="A-1", price="???", condition="A"))
    assert normalized.price.value == ""
    assert normalized.price.confidence == 0.0


def test_records_survive_a_json_roundtrip():
    original = [_record(management_no="A-1", purchased_on="R6.3.5", price="100", condition="A")]
    restored = from_dicts(to_dicts(original))
    assert restored[0].management_no.value == "A-1"
    assert restored[0].price.confidence == 1.0
