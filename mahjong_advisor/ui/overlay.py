"""Always-on-top overlay window with a global hotkey to jump to the input box.

One input box drives everything through the shared AdvisorSession: type a hand
to get a discard suggestion, or a command (`r2`, `d2 3s`, `t 9`, `fold`, ...)
to feed the table state that powers danger reading. A global hotkey refocuses
the box even while the game window has focus, so you don't have to alt-tab
mid-turn.
"""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import font as tkfont

from mahjong_advisor.session import AdvisorSession

DEFAULT_FOCUS_HOTKEY = "<ctrl>+<alt>+h"
DEFAULT_RESET_HOTKEY = "<ctrl>+<alt>+r"
DEFAULT_READ_HOTKEY = "<ctrl>+<alt>+m"

_HINT = "手牌 or コマンド (help)"


class OverlayApp:
    def __init__(
        self,
        focus_hotkey: str = DEFAULT_FOCUS_HOTKEY,
        reset_hotkey: str = DEFAULT_RESET_HOTKEY,
        read_hotkey: str = DEFAULT_READ_HOTKEY,
        geometry: str = "+40+40",
    ) -> None:
        self.session = AdvisorSession()
        self._ui_queue: queue.Queue = queue.Queue()

        self.root = tk.Tk()
        self.root.title("Mahjong Advisor")
        self.root.attributes("-topmost", True)
        self.root.geometry(geometry)
        try:
            self.root.attributes("-alpha", 0.92)
        except tk.TclError:
            pass  # not supported on this platform

        mono = tkfont.Font(family="Consolas", size=11)
        if mono.actual("family") != "Consolas":
            mono = tkfont.Font(family="Courier", size=11)

        frame = tk.Frame(self.root, bg="#1e1e1e", padx=8, pady=6)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=_HINT, fg="white", bg="#1e1e1e", font=mono).grid(
            row=0, column=0, sticky="w"
        )
        self.command_entry = tk.Entry(frame, width=30, font=mono)
        self.command_entry.grid(row=1, column=0, sticky="we", pady=(2, 0))
        self.command_entry.bind("<Return>", self._on_submit)

        self.status = tk.Label(
            frame,
            text=f"画面読取: {read_hotkey}   フォーカス: {focus_hotkey}   リセット: {reset_hotkey}",
            fg="#888888",
            bg="#1e1e1e",
            font=(mono.actual("family"), 8),
        )
        self.status.grid(row=2, column=0, sticky="w", pady=(4, 0))

        self.result_label = tk.Label(
            frame,
            text="手牌を入力してEnter",
            fg="#7fffa0",
            bg="#1e1e1e",
            font=mono,
            justify="left",
            anchor="w",
        )
        self.result_label.grid(row=3, column=0, sticky="w", pady=(6, 0))

        self.command_entry.focus_set()
        self.root.after(50, self._drain_ui_queue)

        self._hotkey_listener = None
        self._focus_hotkey = focus_hotkey
        self._reset_hotkey = reset_hotkey
        self._read_hotkey = read_hotkey

    # -- hotkey wiring -----------------------------------------------------
    def start_global_hotkeys(self) -> None:
        try:
            from pynput import keyboard
        except ImportError:
            self.status.config(text="pynput 未導入のためグローバルホットキーは無効です")
            return

        bindings = {
            self._focus_hotkey: self._request_focus,
            self._reset_hotkey: self._request_reset,
            self._read_hotkey: self._request_screen_read,
        }
        self._hotkey_listener = keyboard.GlobalHotKeys(bindings)
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()

    def _request_focus(self) -> None:
        # Called from the pynput listener thread; hop back onto the Tk thread.
        self._ui_queue.put("focus")

    def _request_reset(self) -> None:
        self._ui_queue.put("reset")

    def _request_screen_read(self) -> None:
        self._ui_queue.put("read")

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                action = self._ui_queue.get_nowait()
                if action == "focus":
                    self._grab_focus()
                elif action == "reset":
                    self._show(self.session.handle("reset"))
                elif action == "read":
                    self.read_screen()
        except queue.Empty:
            pass
        self.root.after(50, self._drain_ui_queue)

    def read_screen(self) -> None:
        """Capture the table, update state and show the advice - the whole turn
        handled by one keystroke."""
        try:
            from mahjong_advisor.config import VisionConfig
            from mahjong_advisor.vision.runner import read_table
        except ImportError as exc:
            self._show(f"画面認識の依存関係が未導入です: {exc}", error=True)
            return

        try:
            self._show(read_table(self.session, VisionConfig.load()))
        except Exception as exc:  # noqa: BLE001 - keep the overlay alive
            self._show(f"エラー: {exc}", error=True)

    def _grab_focus(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.command_entry.focus_force()
        self.command_entry.select_range(0, "end")

    # -- actions -----------------------------------------------------------
    def _show(self, text: str, error: bool = False) -> None:
        self.result_label.config(text=text, fg="#ff8080" if error else "#7fffa0")

    def _on_submit(self, _event: tk.Event) -> None:
        text = self.command_entry.get().strip()
        if not text:
            return
        response = self.session.handle(text)
        self._show(response, error=response.startswith("エラー"))
        # Commands are one-shot; keep the hand text around for quick edits.
        if response.startswith("エラー") or not response.startswith("→"):
            self.command_entry.delete(0, "end")
        else:
            self.command_entry.select_range(0, "end")

    def run(self) -> None:
        self.start_global_hotkeys()
        self.root.mainloop()


def main() -> None:
    OverlayApp().run()


if __name__ == "__main__":
    main()
