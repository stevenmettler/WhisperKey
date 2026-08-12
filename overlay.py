"""
Tiny on-screen status indicator: a small borderless pill near the bottom of
the screen that shows "Recording" (red) while you hold the hotkey and
"Transcribing" (amber) while inference runs, then disappears.

Two things make this safe to use with the paste-on-release flow:

  * It runs its own Tk event loop on a dedicated thread and is driven only
    through a thread-safe queue, so the hotkey callback thread never touches
    Tk directly.
  * The window uses the Win32 WS_EX_NOACTIVATE style so showing it NEVER
    steals focus from your text field — otherwise the simulated Ctrl+V would
    paste into the overlay instead of the app you're typing into.

If anything here fails (no display, Tk missing), it degrades to a no-op; the
core recording loop keeps working.
"""

import queue
import sys
import threading

from app_logging import log

_BG = "#1e1e1e"
_REC = "#e23b3b"
_BUSY = "#e0a020"


class Overlay:
    def __init__(self):
        self._q = queue.Queue()
        self._thread = None
        self._enabled = True

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # --- public, thread-safe API ------------------------------------------
    def show_recording(self):
        self._q.put(("show", "●  Recording", _REC))

    def show_transcribing(self):
        self._q.put(("show", "…  Transcribing", _BUSY))

    def hide(self):
        self._q.put(("hide", None, None))

    # --- Tk thread internals ----------------------------------------------
    def _run(self):
        try:
            import tkinter as tk
        except Exception as e:
            log.warning("overlay disabled (tkinter unavailable): %s", e)
            self._enabled = False
            return

        try:
            self._root = tk.Tk()
            self._root.withdraw()
            self._root.overrideredirect(True)
            self._root.attributes("-topmost", True)
            try:
                self._root.attributes("-alpha", 0.92)
            except Exception:
                pass
            self._dot = tk.Label(
                self._root, text="●  Recording", fg="white", bg=_BG,
                font=("Segoe UI", 12, "bold"), padx=18, pady=10,
            )
            self._dot.pack()
            self._root.update_idletasks()
            self._make_non_activating()
            self._root.after(40, self._poll)
            self._root.mainloop()
        except Exception:
            log.exception("overlay thread crashed; continuing without overlay")
            self._enabled = False

    def _make_non_activating(self):
        """Apply WS_EX_NOACTIVATE + toolwindow so the overlay never takes focus."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_TOPMOST = 0x00000008
            u = ctypes.windll.user32
            hwnd = u.GetParent(self._root.winfo_id()) or self._root.winfo_id()
            style = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
            u.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST,
            )
        except Exception:
            log.debug("could not set WS_EX_NOACTIVATE", exc_info=True)

    def _position(self):
        self._root.update_idletasks()
        w = self._root.winfo_width()
        h = self._root.winfo_height()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = (sw - w) // 2
        y = sh - h - 90  # a bit above the taskbar
        self._root.geometry(f"+{x}+{y}")

    def _poll(self):
        try:
            while True:
                cmd, text, color = self._q.get_nowait()
                if cmd == "show":
                    self._dot.config(text=text, bg=color)
                    self._root.configure(bg=color)
                    self._position()
                    self._root.deiconify()
                    self._root.lift()
                elif cmd == "hide":
                    self._root.withdraw()
        except queue.Empty:
            pass
        self._root.after(40, self._poll)


if __name__ == "__main__":
    # Manual test: shows "Recording" for 3s, then "Transcribing" for 2s, then hides.
    import time

    ov = Overlay()
    ov.start()
    time.sleep(0.5)
    print("showing Recording (red) for 3s...")
    ov.show_recording()
    time.sleep(3)
    print("showing Transcribing (amber) for 2s...")
    ov.show_transcribing()
    time.sleep(2)
    print("hiding.")
    ov.hide()
    time.sleep(1)
