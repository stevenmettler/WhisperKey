"""
System-wide hotkey listener. Works without the app being focused.
Push-to-talk model: on_start fires on key-down, on_stop fires on key-up.

Note: the `keyboard` library's global hooks generally need the process to
run with sufficient privileges on some Windows configurations — if hotkeys
silently don't fire, try running the terminal/app as Administrator first
to rule that out before debugging further.
"""

import keyboard

from app_logging import log
from config import config


class HotkeyBindError(RuntimeError):
    """Raised when the global hotkey hook can't be installed."""


class HotkeyListener:
    def __init__(self, on_start, on_stop, hotkey=None):
        self.hotkey = hotkey or config["hotkey"]
        self.on_start = on_start
        self.on_stop = on_stop
        self._pressed = False

    def _handle_press(self, event):
        # `keyboard` fires on_press repeatedly while a key is held down
        # (OS auto-repeat); the flag ensures on_start runs only once per hold.
        if not self._pressed:
            self._pressed = True
            try:
                self.on_start()
            except Exception:
                log.exception("error in on_start callback")

    def _handle_release(self, event):
        if self._pressed:
            self._pressed = False
            try:
                self.on_stop()
            except Exception:
                log.exception("error in on_stop callback")

    def start(self):
        try:
            keyboard.on_press_key(self.hotkey, self._handle_press)
            keyboard.on_release_key(self.hotkey, self._handle_release)
        except ValueError as e:
            # Unknown key name for the `keyboard` library.
            raise HotkeyBindError(
                f"Hotkey '{self.hotkey}' is not a valid key name. Set a valid "
                "'hotkey' in settings.json (e.g. 'f9', 'scroll lock')."
            ) from e
        except Exception as e:
            # Hook install failed — commonly a privilege issue on Windows, or
            # the key is grabbed by another app.
            raise HotkeyBindError(
                f"Could not install the global hotkey hook for '{self.hotkey}': "
                f"{e}. Try running as Administrator, or check whether another "
                "app has claimed this key."
            ) from e
        log.info("listening for '%s' (hold to record)", self.hotkey)

    def stop(self):
        keyboard.unhook_all()


if __name__ == "__main__":
    # Quick manual test: hold F9, watch the console print start/stop.
    listener = HotkeyListener(
        on_start=lambda: print(">> recording started"),
        on_stop=lambda: print(">> recording stopped"),
    )
    try:
        listener.start()
    except HotkeyBindError as e:
        print(f"ERROR: {e}")
        raise SystemExit(1)
    print(f"Hold {listener.hotkey.upper()} to test. Press Ctrl+C to quit.")
    keyboard.wait()
