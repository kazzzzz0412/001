"""Interactive calibration for the experimental screen-vision mode.

Every online mahjong client uses a different tile skin and hand-row layout,
so there is no universal template set. This tool walks you through: (1)
dragging a box around your own hand row on screen, and (2) capturing that
row a few times while you label each tile slot, building up a folder of
reference tile images (`templates/5m.png`, `templates/1z.png`, ...) that the
recognizer later matches against.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import cv2

from mahjong_advisor.config import CaptureRegion, DEFAULT_CONFIG_PATH, VisionConfig
from mahjong_advisor.vision.capture import grab_region, slice_into_tiles


def select_region_interactively() -> CaptureRegion:
    """Full-screen click-and-drag rectangle selector. Returns screen coordinates."""
    import tkinter as tk

    coords: dict[str, int] = {}
    start: dict[str, int] = {}
    rect_id: dict[str, int | None] = {"id": None}

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    try:
        root.attributes("-alpha", 0.25)
    except tk.TclError:
        pass
    root.attributes("-topmost", True)
    root.configure(bg="gray")
    canvas = tk.Canvas(root, cursor="cross", bg="gray", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    canvas.create_text(
        20, 20, anchor="nw", fill="red",
        text="自分の手札が並んでいる範囲をドラッグしてください（Escで中止）",
        font=("Consolas", 16),
    )

    def on_press(event: tk.Event) -> None:
        start["x"], start["y"] = event.x, event.y
        rect_id["id"] = canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="red", width=2
        )

    def on_drag(event: tk.Event) -> None:
        if rect_id["id"] is not None:
            canvas.coords(rect_id["id"], start["x"], start["y"], event.x, event.y)

    def on_release(event: tk.Event) -> None:
        x0, y0 = start.get("x", event.x), start.get("y", event.y)
        x1, y1 = event.x, event.y
        coords["left"] = root.winfo_rootx() + min(x0, x1)
        coords["top"] = root.winfo_rooty() + min(y0, y1)
        coords["width"] = abs(x1 - x0)
        coords["height"] = abs(y1 - y0)
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", lambda _e: root.destroy())

    root.mainloop()

    if coords.get("width", 0) < 5 or coords.get("height", 0) < 5:
        raise RuntimeError("範囲選択がキャンセル、または小さすぎます。")

    return CaptureRegion(**coords)


def _open_for_preview(path: Path) -> None:
    if sys.platform == "win32":
        import os

        os.startfile(path)  # noqa: S606 - user-triggered, opens their own capture
    else:
        print(f"    (画像を確認: {path})")


def run_calibration(config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    config = VisionConfig.load(config_path)

    print("画面上で自分の手札が並んでいる範囲をドラッグして選択してください。")
    config.hand_region = select_region_interactively()

    tile_count_str = input(f"選択範囲内の牌の枚数 [{config.tile_count}]: ").strip()
    if tile_count_str:
        config.tile_count = int(tile_count_str)

    config.save(config_path)
    print(f"設定を保存しました: {config_path}")

    templates_dir = Path(config.templates_dir)
    templates_dir.mkdir(parents=True, exist_ok=True)

    print("\nこれから手札を撮影してラベル付けします。")
    print("実際のゲーム画面で牌がはっきり見える状態にしてから Enter を押してください。")
    print("(ラベル入力を空Enterでスキップ / 'q' でこのツールを終了)")

    while True:
        cmd = input("\n[Enter]=撮影 / q=終了 > ").strip().lower()
        if cmd == "q":
            break

        image = grab_region(config.hand_region.as_mss_region())
        slots = slice_into_tiles(image, config.tile_count)

        for i, crop in enumerate(slots):
            tmp_path = Path(tempfile.gettempdir()) / f"mahjong_calib_slot_{i}.png"
            cv2.imwrite(str(tmp_path), crop)
            _open_for_preview(tmp_path)
            label = input(f"  牌 {i + 1}/{len(slots)} のラベル (例: 5m, 1z): ").strip()
            if not label:
                continue
            out_path = templates_dir / f"{label}.png"
            cv2.imwrite(str(out_path), crop)
            print(f"    保存: {out_path}")

    print("キャリブレーション終了。'python main.py vision' で認識を試せます。")


if __name__ == "__main__":
    run_calibration()
