"""Read the table off the screen and run it through the advisor.

One call reads your hand and every calibrated discard pile, folds the piles into
the session's table state, and returns the advice - so a single keystroke during
your turn gives you the answer without typing anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from mahjong_advisor.config import DEFAULT_CONFIG_PATH, VisionConfig
from mahjong_advisor.formatting import format_analysis
from mahjong_advisor.session import AdvisorSession
from mahjong_advisor.vision.capture import grab_region
from mahjong_advisor.vision.recognizer import (
    labels_to_hand_string,
    labels_to_tiles,
    load_templates,
    recognize_hand,
    recognize_pile,
)
from mahjong_advisor.vision.sync import PileSync, describe_syncs, sync_pile


class CalibrationError(RuntimeError):
    """The screen can't be read yet because calibration is missing."""


@dataclass
class ScreenRead:
    hand_string: str = ""
    syncs: list[PileSync] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _require_templates(config: VisionConfig) -> dict:
    templates = load_templates(config.templates_dir)
    if not templates:
        raise CalibrationError(
            "テンプレートが空です。`python main.py calibrate` で牌画像を登録してください。"
        )
    return templates


def read_hand(config: VisionConfig, templates: dict) -> str:
    if config.hand_region is None:
        raise CalibrationError(
            "手牌の範囲が未設定です。先に `python main.py calibrate` を実行してください。"
        )

    image = grab_region(config.hand_region.as_mss_region())
    labels, unmatched = recognize_hand(image, config.tile_count, templates, config.match_threshold)

    if unmatched:
        positions = ", ".join(str(i + 1) for i in unmatched)
        raise CalibrationError(
            f"手牌の{len(unmatched)}枚を認識できませんでした（{positions}番目）。"
            " calibrate でテンプレートを追加するか、手入力してください。"
        )
    return labels_to_hand_string([label for label in labels if label])


def read_piles(config: VisionConfig, templates: dict, session: AdvisorSession) -> ScreenRead:
    """Read every calibrated discard pile and fold it into the table state."""
    result = ScreenRead()
    for player, grid in sorted(config.discard_regions.items()):
        image = grab_region(grid.as_mss_region())
        labels, unreadable = recognize_pile(
            image, grid.columns, grid.rows, templates, config.match_threshold
        )
        label_name = session.table.opponents[player - 1].label
        if unreadable:
            # An upright template can't match the sideways riichi tile.
            result.warnings.append(
                f"{label_name}の河に読めないセルがあります（リーチ宣言牌かも: r{player} で記録）"
            )
        result.syncs.append(sync_pile(session.table, player, labels_to_tiles(labels)))
    return result


def read_table(session: AdvisorSession, config: VisionConfig) -> str:
    """Full screen read: hand + piles -> advice text."""
    templates = _require_templates(config)
    read = read_piles(config, templates, session)
    hand_string = read_hand(config, templates)

    lines = []
    if config.discard_regions:
        lines.append(describe_syncs(read.syncs, session.table))
    lines.extend(read.warnings)
    lines.append(f"認識した手牌: {hand_string}")
    lines.append("")

    result = session.advisor.analyze(hand_string, table=session.table, stance=session.stance)
    lines.append(format_analysis(result))
    return "\n".join(lines)


def run_vision_once(config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    session = AdvisorSession()
    config = VisionConfig.load(config_path)
    try:
        print(read_table(session, config))
    except Exception as exc:  # noqa: BLE001 - surface to the user, keep going
        print(f"エラー: {exc}")


def run_vision_watch(config_path: Path = DEFAULT_CONFIG_PATH, hotkey: str = "<ctrl>+<alt>+m") -> None:
    """Keep one table state alive and re-read the screen on every hotkey press."""
    from pynput import keyboard

    session = AdvisorSession()
    config = VisionConfig.load(config_path)
    print(f"ホットキー {hotkey} を押すと、今の画面から手牌と河を読み取って解析します。")
    print("(Ctrl+C で終了 / 新しい局に移ったら再起動するか overlay モードの reset を使ってください)")

    def on_hotkey() -> None:
        try:
            print("\n" + read_table(session, config))
        except Exception as exc:  # noqa: BLE001
            print(f"エラー: {exc}")

    listener = keyboard.GlobalHotKeys({hotkey: on_hotkey})
    listener.start()
    listener.join()


if __name__ == "__main__":
    run_vision_once()
