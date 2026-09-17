"""Command line for filling an inventory sheet from sticker photos.

Writing is opt-in. Every run prints the exact cells it would change and stops
there unless `--apply` is passed, because the thing on the other end is
somebody's real inventory and a misread "1" for "7" should be caught on screen
rather than in the sheet.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .config import DEFAULT_CONFIG_PATH, SheetConfig
from .planner import FIELD_LABELS, Plan, build_plan
from .records import StickerRecord, from_dicts, normalize_record, to_dicts
from .reader import DEFAULT_MODEL, find_images, read_stickers
from .targets import open_target


def _print_plan(plan: Plan, records: list[StickerRecord], config: SheetConfig) -> None:
    print(f"\n読み取ったステッカー: {len(records)}件")

    if plan.missing_columns:
        print(f"\n[!] シートに見つからない列: {', '.join(plan.missing_columns)}")
        print("    inventory.json の見出し名を実際のシートに合わせてください。")

    if plan.edits:
        print(f"\n書き込み予定: {len(plan.edits)}セル")
        print(f"  {'セル':<8} {'管理番号':<14} {'項目':<8} {'値':<14} 確信度")
        for edit in plan.edits:
            label = FIELD_LABELS.get(edit.field_name, "要確認メモ")
            mark = " *" if edit.confidence < config.confidence_threshold else ""
            print(
                f"  {edit.a1:<8} {edit.management_no:<14} {label:<8} "
                f"{edit.value:<14} {edit.confidence:.2f}{mark}"
            )
    else:
        print("\n書き込むセルはありません。")

    if plan.review:
        print(f"\n[*] 目視確認したい項目: {len(plan.review)}件")
        for item in plan.review:
            label = FIELD_LABELS.get(item.field_name, item.field_name)
            note = f" - {item.note}" if item.note else ""
            print(f"  {item.row}行 {item.management_no} {label}: "
                  f"'{item.value}' (確信度 {item.confidence:.2f}){note}")

    if plan.conflicts:
        print(f"\n[!] 既に値が入っているので書き換えませんでした: {len(plan.conflicts)}件")
        for conflict in plan.conflicts:
            label = FIELD_LABELS.get(conflict.field_name, conflict.field_name)
            print(
                f"  {conflict.a1} {conflict.management_no} {label}: "
                f"既存 '{conflict.existing}' / 読み取り '{conflict.proposed}'"
            )
        print("    上書きしたい場合は inventory.json の overwrite を true にしてください。")

    if plan.unmatched:
        print(f"\n[!] シートの行と結び付けられませんでした: {len(plan.unmatched)}件")
        for key in plan.unmatched:
            print(f"  {key}")


def _collect_images(specs: list[str]) -> list[Path]:
    images: list[Path] = []
    for spec in specs:
        path = Path(spec)
        if not path.exists():
            raise FileNotFoundError(f"見つかりません: {spec}")
        images.extend(find_images(path))
    return images


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python main.py inventory",
        description="手書きの在庫表ステッカーを読み取ってスプレッドシートに記入します",
    )
    parser.add_argument(
        "--images", action="append", default=[], metavar="PATH",
        help="ステッカー写真のファイルまたはフォルダ（複数指定可）",
    )
    parser.add_argument(
        "--target", metavar="SPEC",
        help="書き込み先。sheet:<スプレッドシートID> または book:<ファイル.xlsx>。"
             "末尾に #シート名 を付けるとタブを指定できます",
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="列の対応表(JSON)")
    parser.add_argument(
        "--credentials", default=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ""),
        help="Googleサービスアカウントの鍵ファイル",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="読み取りに使うモデル")
    parser.add_argument("--save-read", metavar="PATH", help="読み取り結果をJSONに保存する")
    parser.add_argument(
        "--from-read", metavar="PATH",
        help="保存済みJSONから読み込む（写真を読み直さないので無料でやり直せます）",
    )
    parser.add_argument("--apply", action="store_true", help="実際にシートへ書き込む")
    parser.add_argument(
        "--init-config", action="store_true", help="設定ファイルの雛形を作って終了する"
    )
    args = parser.parse_args(argv)

    config_path = Path(args.config)

    if args.init_config:
        if config_path.exists():
            print(f"既にあります: {config_path}")
            return 1
        SheetConfig().save(config_path)
        print(f"設定ファイルを作りました: {config_path}")
        print("実際のシートの見出しに合わせて columns を書き換えてください。")
        return 0

    config = SheetConfig.load(config_path)

    if args.from_read:
        raw_records = from_dicts(json.loads(Path(args.from_read).read_text(encoding="utf-8")))
    elif args.images:
        images = _collect_images(args.images)
        if not images:
            print("画像が見つかりませんでした。", file=sys.stderr)
            return 1
        print(f"{len(images)}枚の写真を読み取ります…")
        raw_records = read_stickers(images, model=args.model)
    else:
        parser.error("--images か --from-read のどちらかを指定してください")

    if args.save_read:
        Path(args.save_read).write_text(
            json.dumps(to_dicts(raw_records), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"読み取り結果を保存しました: {args.save_read}")

    records = [
        normalize_record(
            record,
            date_format=config.date_format,
            condition_aliases=config.condition_aliases,
        )
        for record in raw_records
    ]

    if not args.target:
        print("\n--target が未指定のため、読み取り結果のみ表示します。")
        for record in records:
            values = "  ".join(f"{FIELD_LABELS[n]}={v.value!r}" for n, v in record.fields().items())
            print(f"  [{record.source_image}] {values}")
        return 0

    target = open_target(
        args.target, credentials_path=args.credentials, date_format=config.date_format
    )
    print(f"書き込み先: {target.describe()}")

    grid = target.read_grid()
    plan = build_plan(grid, records, config)
    _print_plan(plan, records, config)

    if plan.missing_columns:
        return 1

    if not args.apply:
        print("\n(下書きです。実際に書き込むには --apply を付けてください)")
        return 0

    if plan.is_empty:
        return 0

    target.apply(plan.edits)
    highlights = [
        (edit.row, edit.column)
        for edit in plan.edits
        if edit.field_name != "_review" and edit.confidence < config.confidence_threshold
    ]
    target.highlight(highlights)
    print(f"\n{len(plan.edits)}セルを書き込みました。")
    if highlights:
        print(f"うち{len(highlights)}セルは確信度が低いため色を付けました。目視で確認してください。")
    return 0
