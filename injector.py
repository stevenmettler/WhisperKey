"""
Pushes transcribed text into whatever app currently has focus.
Clipboard + simulated Ctrl+V is the most reliable approach across
arbitrary Windows apps (browsers, Slack, VS Code, Office, etc.) —
character-by-character SendInput typing is flakier in some Electron apps.

Clipboard restore: we save the user's existing clipboard, paste our text,
then put the original back. The restore must wait long enough for the target
app to actually consume the paste first — otherwise we race and restore the
old clipboard before Ctrl+V has been processed, and the wrong text lands.
"""

import time

import keyboard
import pyperclip

from app_logging import log


def inject_text(
    text: str,
    restore_clipboard: bool = True,
    paste_delay: float = 0.05,
    restore_delay: float = 0.35,
):
    if not text:
        return

    original_clipboard = None
    if restore_clipboard:
        try:
            original_clipboard = pyperclip.paste()
        except pyperclip.PyperclipException as e:
            # Clipboard may be empty or hold non-text data — fine to skip restore.
            log.debug("could not read clipboard for restore: %s", e)
            original_clipboard = None

    try:
        pyperclip.copy(text)
    except pyperclip.PyperclipException as e:
        log.error("failed to set clipboard, cannot inject text: %s", e)
        return

    time.sleep(paste_delay)  # let the clipboard settle before pasting
    keyboard.send("ctrl+v")

    if restore_clipboard and original_clipboard is not None:
        # Wait for the target app to consume the paste before restoring, so we
        # don't overwrite the clipboard out from under an in-flight Ctrl+V.
        time.sleep(restore_delay)
        try:
            pyperclip.copy(original_clipboard)
        except pyperclip.PyperclipException as e:
            log.debug("could not restore original clipboard: %s", e)


if __name__ == "__main__":
    # Quick manual test: focus a text field, then run this — it'll paste after 3s.
    print("Focus a text field. Injecting test text in 3 seconds...")
    time.sleep(3)
    inject_text("Hello from WhisperKey!")
    print("Done. Check that the text pasted and your clipboard is unchanged.")
