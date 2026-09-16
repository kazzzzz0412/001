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

from mahjong_advisor.config import CaptureRegion, DEFAULT_CONFIG_PATH, GridRegion, VisionConfig
from mahjong_advisor.vision.capture import grab_region, slice_into_grid, slice_into_tiles
from mahjong_advisor.vision.recognizer import EMPTY_LABEL

PLAYER_LABELS = {1: "下家(右)", 2: "対面", 3: "上家(左)"}


def select_region_interactively(prompt: str = "範囲をドラッグしてください（Escで中止）") -> CaptureRegion:
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
    canvas.create_text(20, 20, anchor="nw", fill="red", text=prompt, font=("Consolas", 16))

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


def _label_crops(crops: list, templates_dir: Path, caption: str) -> None:
    """Show each crop and save whatever label the user types for it."""
    for i, crop in enumerate(crops):
        tmp_path = Path(tempfile.gettempdir()) / f"mahjong_calib_{i}.png"
        cv2.imwrite(str(tmp_path), crop)
        _open_for_preview(tmp_path)
        label = input(f"  {caption} {i + 1}/{len(crops)} のラベル: ").strip()
        if not label:
            continue
        out_path = templates_dir / f"{label}.png"
        cv2.imwrite(str(out_path), crop)
        print(f"    保存: {out_path}")


def calibrate_regions(config: VisionConfig, config_path: Path) -> None:
    """Step 1: where on screen your hand and each discard pile are."""
    print("\n[1/2] 範囲の設定")
    print("まず自分の手牌が並んでいる範囲をドラッグして選択してください。")
    config.hand_region = select_region_interactively(
        "自分の手牌の範囲をドラッグ（Escで中止）"
    )
    tile_count_str = input(f"手牌の範囲に入る牌の枚数 [{config.tile_count}]: ").strip()
    if tile_count_str:
        config.tile_count = int(tile_count_str)

    print("\n続いて各家の河（捨て牌置き場）の範囲を設定します。")
    print("設定した家だけ自動で読み取ります。スキップしたい家は 'n' を入力してください。")
    for player, label in PLAYER_LABELS.items():
        answer = input(f"  {label} の河を設定しますか？ [Y/n]: ").strip().lower()
        if answer == "n":
            config.discard_regions.pop(player, None)
            continue

        region = select_region_interactively(f"{label} の河全体をドラッグ（Escで中止）")
        columns = input("    横の列数 [6]: ").strip() or "6"
        rows = input("    縦の段数 [3]: ").strip() or "3"
        config.discard_regions[player] = GridRegion(
            left=region.left,
            top=region.top,
            width=region.width,
            height=region.height,
            columns=int(columns),
            rows=int(rows),
        )

    config.save(config_path)
    print(f"設定を保存しました: {config_path}")


def calibrate_templates(config: VisionConfig) -> None:
    """Step 2: what each tile looks like in your client's skin."""
    templates_dir = Path(config.templates_dir)
    templates_dir.mkdir(parents=True, exist_ok=True)

    print("\n[2/2] 牌画像の登録")
    print("実際の対局画面で牌がはっきり見える状態にしてから撮影してください。")
    print("1回で全種類は揃いません。何局かに分けて出てきた牌を登録していけばOKです。")
    print("ラベル例: 5m / 1z / 0p(赤5) 、空Enterでその牌はスキップ")
    print(
        f"重要: 河の空きマスを1つ '{EMPTY_LABEL}' というラベルで登録してください。"
        "これが無いと空きマスを牌と誤認します。"
    )

    while True:
        choice = input(
            "\n[h]=手牌を撮影 / [1][2][3]=各家の河を撮影 / [q]=終了 > "
        ).strip().lower()
        if choice == "q":
            break

        if choice == "h":
            if config.hand_region is None:
                print("  手牌の範囲が未設定です。")
                continue
            image = grab_region(config.hand_region.as_mss_region())
            _label_crops(slice_into_tiles(image, config.tile_count), templates_dir, "手牌")
        elif choice in ("1", "2", "3"):
            player = int(choice)
            grid = config.discard_regions.get(player)
            if grid is None:
                print(f"  {PLAYER_LABELS[player]} の河は未設定です。")
                continue
            image = grab_region(grid.as_mss_region())
            cells = slice_into_grid(image, grid.columns, grid.rows)
            _label_crops(cells, templates_dir, f"{PLAYER_LABELS[player]}の河")
        else:
            print("  h / 1 / 2 / 3 / q のいずれかを入力してください。")


def run_calibration(config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    config = VisionConfig.load(config_path)
    calibrate_regions(config, config_path)
    calibrate_templates(config)
    print("\nキャリブレーション終了。")
    print("'python main.py vision' で1回読み取り、'python main.py vision --watch' で")
    print("ホットキー(Ctrl+Alt+M)を押すたびに読み取れます。")


if __name__ == "__main__":
    run_calibration()
