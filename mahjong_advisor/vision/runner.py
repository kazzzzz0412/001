"""Capture the calibrated hand region, recognize it, and run it through the advisor."""

from __future__ import annotations

from pathlib import Path

from mahjong_advisor.config import DEFAULT_CONFIG_PATH, VisionConfig
from mahjong_advisor.engine.advisor import Advisor
from mahjong_advisor.formatting import format_analysis
from mahjong_advisor.vision.capture import grab_region
from mahjong_advisor.vision.recognizer import labels_to_hand_string, load_templates, recognize_hand


def analyze_screen_once(config: VisionConfig) -> str:
    if config.hand_region is None:
        raise RuntimeError("キャリブレーション未実施です。先に `python main.py calibrate` を実行してください。")

    templates = load_templates(config.templates_dir)
    if not templates:
        raise RuntimeError("テンプレートが空です。`python main.py calibrate` で牌画像を登録してください。")

    image = grab_region(config.hand_region.as_mss_region())
    labels, unmatched = recognize_hand(image, config.tile_count, templates, config.match_threshold)

    if unmatched:
        positions = ", ".join(str(i + 1) for i in unmatched)
        raise RuntimeError(
            f"{len(unmatched)}枚の牌を認識できませんでした（{positions}番目）。"
            " calibrate でテンプレートを追加するか、手入力モードを使ってください。"
        )

    hand_string = labels_to_hand_string([label for label in labels if label])
    result = Advisor().analyze(hand_string)
    return f"認識した手札: {hand_string}\n\n{format_analysis(result)}"


def run_vision_once(config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    config = VisionConfig.load(config_path)
    try:
        print(analyze_screen_once(config))
    except Exception as exc:  # noqa: BLE001 - surface to the user, keep the process alive
        print(f"エラー: {exc}")


def run_vision_watch(config_path: Path = DEFAULT_CONFIG_PATH, hotkey: str = "<ctrl>+<alt>+m") -> None:
    from pynput import keyboard

    config = VisionConfig.load(config_path)
    print(f"ホットキー {hotkey} を押すと、今の画面から手札を読み取って解析します。(Ctrl+C で終了)")

    def on_hotkey() -> None:
        try:
            print("\n" + analyze_screen_once(config))
        except Exception as exc:  # noqa: BLE001
            print(f"エラー: {exc}")

    listener = keyboard.GlobalHotKeys({hotkey: on_hotkey})
    listener.start()
    listener.join()


if __name__ == "__main__":
    run_vision_once()
