from inventory_filler.config import SheetConfig
from inventory_filler.planner import (
    build_plan,
    column_index,
    column_letter,
    resolve_columns,
)
from inventory_filler.records import FieldValue, StickerRecord

HEADER = ["管理番号", "商品名", "仕入日", "仕入価格", "状態", "要確認"]


def _grid(*rows):
    return [list(HEADER), *[list(row) for row in rows]]


def _config(**kwargs):
    base = dict(
        key_column="管理番号",
        columns={"purchased_on": "仕入日", "price": "仕入価格", "condition": "状態"},
        review_column="要確認",
    )
    base.update(kwargs)
    return SheetConfig(**base)


def _record(no, purchased_on="2024/03/05", price="1200", condition="A", confidence=1.0):
    def value(text):
        return FieldValue(value=text, confidence=confidence, raw=text)

    return StickerRecord(
        management_no=value(no),
        purchased_on=value(purchased_on),
        price=value(price),
        condition=value(condition),
        source_image="sticker.jpg",
    )


def test_column_letter_roundtrip():
    for index in (1, 26, 27, 52, 703):
        assert column_index(column_letter(index)) == index


def test_resolve_columns_matches_header_text():
    resolved, missing = resolve_columns(_grid(), _config())
    assert missing == []
    assert resolved["management_no"] == 1
    assert resolved["price"] == 4


def test_resolve_columns_falls_back_to_a_column_letter():
    grid = [["", "", "", ""]]  # a sheet with no usable headers
    resolved, missing = resolve_columns(
        grid, _config(key_column="A", columns={"price": "D"}, review_column="")
    )
    assert missing == []
    assert resolved == {"management_no": 1, "price": 4}


def test_resolve_columns_prefers_a_real_header_named_like_a_letter():
    grid = [["C", "管理番号"]]
    resolved, _ = resolve_columns(
        grid, _config(key_column="管理番号", columns={"price": "C"}, review_column="")
    )
    assert resolved["price"] == 1  # the header "C", not column C


def test_resolve_columns_reports_a_header_it_cannot_find():
    _, missing = resolve_columns(_grid(), _config(columns={"price": "仕入れ額"}))
    assert missing == ["仕入れ額"]


def test_build_plan_fills_the_row_matching_the_management_number():
    grid = _grid(["A-1", "花瓶", "", "", "", ""], ["A-2", "皿", "", "", "", ""])
    plan = build_plan(grid, [_record("A-2")], _config())

    assert [(edit.a1, edit.value) for edit in plan.edits] == [
        ("C3", "2024/03/05"),
        ("D3", "1200"),
        ("E3", "A"),
    ]
    assert plan.unmatched == []


def test_build_plan_matches_despite_width_and_spacing_differences():
    grid = _grid([" Ａ-１ ", "花瓶", "", "", "", ""])
    plan = build_plan(grid, [_record("a-1")], _config())
    assert [edit.row for edit in plan.edits] == [2, 2, 2]


def test_build_plan_appends_an_unknown_management_number():
    grid = _grid(["A-1", "花瓶", "", "", "", ""])
    plan = build_plan(grid, [_record("A-9")], _config())

    key_edit = plan.edits[0]
    assert (key_edit.a1, key_edit.value, key_edit.new_row) == ("A3", "A-9", True)
    assert all(edit.row == 3 for edit in plan.edits)


def test_build_plan_reports_unknown_numbers_when_appending_is_off():
    grid = _grid(["A-1", "花瓶", "", "", "", ""])
    plan = build_plan(grid, [_record("A-9")], _config(append_unknown=False))
    assert plan.edits == []
    assert plan.unmatched == ["A-9"]


def test_build_plan_never_overwrites_an_existing_value_by_default():
    grid = _grid(["A-1", "花瓶", "2020/01/01", "", "", ""])
    plan = build_plan(grid, [_record("A-1")], _config())

    assert [edit.a1 for edit in plan.edits] == ["D2", "E2"]
    assert len(plan.conflicts) == 1
    conflict = plan.conflicts[0]
    assert (conflict.a1, conflict.existing, conflict.proposed) == ("C2", "2020/01/01", "2024/03/05")


def test_build_plan_overwrites_when_explicitly_allowed():
    grid = _grid(["A-1", "花瓶", "2020/01/01", "", "", ""])
    plan = build_plan(grid, [_record("A-1")], _config(overwrite=True))
    assert ("C2", "2024/03/05") in [(edit.a1, edit.value) for edit in plan.edits]
    assert plan.conflicts == []


def test_build_plan_skips_a_cell_that_already_holds_the_same_value():
    grid = _grid(["A-1", "花瓶", "2024/03/05", "1200", "A", ""])
    plan = build_plan(grid, [_record("A-1")], _config())
    assert plan.edits == []
    assert plan.conflicts == []


def test_build_plan_flags_and_annotates_low_confidence_readings():
    grid = _grid(["A-1", "花瓶", "", "", "", ""])
    plan = build_plan(grid, [_record("A-1", confidence=0.5)], _config())

    assert {item.field_name for item in plan.review} >= {"purchased_on", "price", "condition"}
    note = next(edit for edit in plan.edits if edit.field_name == "_review")
    assert note.a1 == "F2"
    assert note.value.startswith("要確認:")


def test_build_plan_leaves_no_review_note_when_everything_was_legible():
    grid = _grid(["A-1", "花瓶", "", "", "", ""])
    plan = build_plan(grid, [_record("A-1")], _config())
    assert plan.review == []
    assert all(edit.field_name != "_review" for edit in plan.edits)


def test_build_plan_skips_blank_fields():
    grid = _grid(["A-1", "花瓶", "", "", "", ""])
    plan = build_plan(grid, [_record("A-1", price="", condition="")], _config())
    assert [edit.field_name for edit in plan.edits] == ["purchased_on"]


def test_build_plan_reports_a_record_with_no_management_number():
    plan = build_plan(_grid(), [_record("")], _config())
    assert plan.edits == []
    assert plan.unmatched == ["sticker.jpg"]


def test_build_plan_stops_when_the_key_column_is_missing():
    plan = build_plan([["品名", "値段"]], [_record("A-1")], _config())
    assert plan.edits == []
    assert "管理番号" in plan.missing_columns


def test_build_plan_tolerates_ragged_rows():
    grid = [list(HEADER), ["A-1"]]  # a row that simply stops early
    plan = build_plan(grid, [_record("A-1")], _config())
    assert [edit.a1 for edit in plan.edits] == ["C2", "D2", "E2"]


def test_build_plan_is_a_no_op_against_an_already_filled_sheet():
    # Re-running must not rewrite cells - including the review note, which is
    # the tool's own column and so has no conflict to protect it.
    grid = _grid(["A-1", "花瓶", "", "", "", ""])
    record = _record("A-1", confidence=0.5)
    config = _config()

    first = build_plan(grid, [record], config)
    for edit in first.edits:
        while len(grid[edit.row - 1]) < edit.column:
            grid[edit.row - 1].append("")
        grid[edit.row - 1][edit.column - 1] = edit.value

    assert build_plan(grid, [record], config).edits == []


def test_build_plan_refreshes_a_review_note_that_changed():
    grid = _grid(["A-1", "花瓶", "", "", "", "要確認: 価格"])
    plan = build_plan(grid, [_record("A-1", confidence=0.5)], _config())
    note = next(edit for edit in plan.edits if edit.field_name == "_review")
    assert note.value == "要確認: 管理番号、仕入日、価格、状態"
