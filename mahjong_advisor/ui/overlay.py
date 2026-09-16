"""Always-on-top overlay window with a global hotkey to jump to the input box.

Manual-input mode: you type your hand (mpsz notation) into a small always-on-top
box and get the ranked discard suggestion instantly. A global hotkey refocuses
the input box even while the game window has focus, so you don't have to
alt-tab mid-turn.
"""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import font as tkfont

from mahjong_advisor.engine.advisor import Advisor
from mahjong_advisor.formatting import format_analysis

DEFAULT_FOCUS_HOTKEY = "<ctrl>+<alt>+h"
DEFAULT_RESET_HOTKEY = "<ctrl>+<alt>+r"


class OverlayApp:
    def __init__(
        self,
        focus_hotkey: str = DEFAULT_FOCUS_HOTKEY,
        reset_hotkey: str = DEFAULT_RESET_HOTKEY,
        geometry: str = "+40+40",
    ) -> None:
        self.advisor = Advisor()
        self.visible = [0] * 34
        self._ui_queue: queue.Queue = queue.Queue()

        self.root = tk.Tk()
        self.root.title("Mahjong Advisor")
        self.root.attributes("-topmost", True)
        self.root.geometry(geometry)
        self.root.resizable(False, False)
        try:
            self.root.attributes("-alpha", 0.92)
        except tk.TclError:
            pass  # not supported on this platform

        mono = tkfont.Font(family="Consolas", size=11)
        if mono.actual("family") != "Consolas":
            mono = tkfont.Font(family="Courier", size=11)

        frame = tk.Frame(self.root, bg="#1e1e1e", padx=8, pady=6)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="手札 (mpsz):", fg="white", bg="#1e1e1e", font=mono).grid(
            row=0, column=0, sticky="w"
        )
        self.hand_entry = tk.Entry(frame, width=24, font=mono)
        self.hand_entry.grid(row=0, column=1, sticky="w", padx=(4, 0))
        self.hand_entry.bind("<Return>", self._on_submit_hand)

        tk.Label(frame, text="見えている牌を追加:", fg="white", bg="#1e1e1e", font=mono).grid(
            row=1, column=0, sticky="w", pady=(4, 0)
        )
        self.visible_entry = tk.Entry(frame, width=24, font=mono)
        self.visible_entry.grid(row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))
        self.visible_entry.bind("<Return>", self._on_submit_visible)

        self.status = tk.Label(
            frame,
            text=f"フォーカスホットキー: {focus_hotkey}  リセット: {reset_hotkey}",
            fg="#888888",
            bg="#1e1e1e",
            font=(mono.actual("family"), 8),
        )
        self.status.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        self.result_label = tk.Label(
            frame,
            text="手札を入力してEnter",
            fg="#7fffa0",
            bg="#1e1e1e",
            font=mono,
            justify="left",
            anchor="w",
        )
        self.result_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self.hand_entry.focus_set()
        self.root.after(50, self._drain_ui_queue)

        self._hotkey_listener = None
        self._focus_hotkey = focus_hotkey
        self._reset_hotkey = reset_hotkey

    # -- hotkey wiring -----------------------------------------------------
    def start_global_hotkeys(self) -> None:
        try:
            from pynput import keyboard
        except ImportError:
            self.status.config(
                text="pynput 未導入のためグローバルホットキーは無効です"
            )
            return

        bindings = {
            self._focus_hotkey: self._request_focus,
            self._reset_hotkey: self._request_reset,
        }
        self._hotkey_listener = keyboard.GlobalHotKeys(bindings)
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()

    def _request_focus(self) -> None:
        # Called from the pynput listener thread; hop back onto the Tk thread.
        self._ui_queue.put(("focus", None))

    def _request_reset(self) -> None:
        self._ui_queue.put(("reset", None))

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                action, _ = self._ui_queue.get_nowait()
                if action == "focus":
                    self._grab_focus()
                elif action == "reset":
                    self._do_reset()
        except queue.Empty:
            pass
        self.root.after(50, self._drain_ui_queue)

    def _grab_focus(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.hand_entry.focus_force()
        self.hand_entry.select_range(0, "end")

    # -- actions -------------------------------------------------------------
    def _do_reset(self) -> None:
        self.visible = [0] * 34
        self.result_label.config(text="見えている牌をリセットしました。")

    def _on_submit_hand(self, _event: tk.Event) -> None:
        text = self.hand_entry.get().strip()
        if not text:
            return
        try:
            result = self.advisor.analyze(text, visible=self.visible)
        except Exception as exc:  # noqa: BLE001 - show parse/validation errors inline
            self.result_label.config(text=f"エラー: {exc}", fg="#ff8080")
            return
        self.result_label.config(text=format_analysis(result), fg="#7fffa0")

    def _on_submit_visible(self, _event: tk.Event) -> None:
        from mahjong.tile import TilesConverter

        text = self.visible_entry.get().strip()
        if not text:
            return
        try:
            added = TilesConverter.one_line_string_to_34_array(text, has_aka_dora=True)
        except Exception as exc:  # noqa: BLE001
            self.result_label.config(text=f"エラー: {exc}", fg="#ff8080")
            return
        for i in range(34):
            self.visible[i] += added[i]
        self.visible_entry.delete(0, "end")
        self.result_label.config(text="見えている牌を追加しました。", fg="#7fffa0")

    def run(self) -> None:
        self.start_global_hotkeys()
        self.root.mainloop()


def main() -> None:
    OverlayApp().run()


if __name__ == "__main__":
    main()
