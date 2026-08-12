"""
Entry point. Wires together: hotkey -> record -> transcribe -> inject,
plus a system tray icon for status/quit.

Run with: python main.py

Failures are surfaced two ways: a Windows tray notification (so you see them
even with no console) and the log file (%LOCALAPPDATA%\\WhisperKey\\whisperkey.log).
"""

import threading

import pystray
from PIL import Image, ImageDraw

from app_logging import log
from audio_capture import AudioRecorder, NoInputDeviceError
from config import config
from hotkey_listener import HotkeyBindError, HotkeyListener
from injector import inject_text
from overlay import Overlay
from transcriber import ModelLoadError, Transcriber

IDLE_COLOR = (70, 70, 70)
RECORDING_COLOR = (220, 60, 60)
ERROR_COLOR = (210, 160, 40)


class WhisperKeyApp:
    def __init__(self):
        self.recorder = AudioRecorder()
        self.transcriber = None  # loaded lazily in a background thread, see run()
        self.model_error = None  # set if the model fails to load
        self.tray_icon = None
        self._recording_active = False
        self.overlay = Overlay() if config.get("show_overlay", True) else None

    def _make_icon_image(self, color):
        # RGBA so the disc sits on a transparent background (the earlier RGB +
        # 4-tuple fill was invalid and raised at startup).
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((8, 8, 56, 56), fill=color)
        return img

    def _set_tray_state(self, color):
        if self.tray_icon:
            self.tray_icon.icon = self._make_icon_image(color)

    def _notify(self, message, title="WhisperKey"):
        """Surface a message to the user (tray balloon) and the log."""
        log.info("notify: %s", message)
        if self.tray_icon is not None:
            try:
                self.tray_icon.notify(message, title)
            except Exception:
                log.exception("tray notify failed")

    def on_hotkey_start(self):
        if self.model_error is not None:
            self._notify(f"Model unavailable: {self.model_error}")
            return
        if self.transcriber is None:
            log.info("model still loading, ignoring key press")
            return
        try:
            self.recorder.start()
        except NoInputDeviceError as e:
            self._notify(str(e), title="WhisperKey — no microphone")
            return
        self._recording_active = True
        self._set_tray_state(RECORDING_COLOR)
        if self.overlay:
            self.overlay.show_recording()

    def on_hotkey_stop(self):
        if not self._recording_active:
            return
        self._recording_active = False
        audio = self.recorder.stop()
        self._set_tray_state(IDLE_COLOR)

        if len(audio) < config["sample_rate"] * 0.3:
            # Too short to be real speech (< ~0.3s) — skip, avoids
            # transcribing accidental taps as hallucinated text.
            log.info("recording too short, skipping")
            if self.overlay:
                self.overlay.hide()
            return

        if self.overlay:
            self.overlay.show_transcribing()

        # Transcribe + inject off the hotkey callback thread so we don't
        # block the global key hook while inference runs.
        threading.Thread(
            target=self._transcribe_and_inject, args=(audio,), daemon=True
        ).start()

    def _transcribe_and_inject(self, audio):
        try:
            try:
                text = self.transcriber.transcribe(audio)
            except Exception:
                log.exception("transcription failed")
                self._notify("Transcription failed — see the log for details.")
                return
            log.info("transcribed: %r", text)
            if text:
                try:
                    inject_text(text)
                except Exception:
                    log.exception("text injection failed")
                    self._notify("Could not paste the transcript — see the log.")
        finally:
            if self.overlay:
                self.overlay.hide()

    def _load_model_background(self):
        try:
            self.transcriber = Transcriber()
            log.info("ready — hold hotkey to dictate")
        except ModelLoadError as e:
            self.model_error = str(e)
            log.error("model load failed: %s", e)
            self._set_tray_state(ERROR_COLOR)
            self._notify(str(e), title="WhisperKey — model failed to load")
        except Exception as e:
            self.model_error = str(e)
            log.exception("unexpected error loading model")
            self._set_tray_state(ERROR_COLOR)
            self._notify(f"Unexpected model error: {e}")

    def _quit(self, icon, item):
        icon.stop()

    def run(self):
        if self.overlay:
            self.overlay.start()

        # Load the (possibly large, first-run-downloads-from-HF) model
        # in the background so the tray icon appears immediately.
        threading.Thread(target=self._load_model_background, daemon=True).start()

        listener = HotkeyListener(on_start=self.on_hotkey_start, on_stop=self.on_hotkey_stop)
        try:
            listener.start()
        except HotkeyBindError as e:
            # No hook = the app can't do anything; make it loud and bail.
            log.error("hotkey bind failed: %s", e)
            self._notify(str(e), title="WhisperKey — hotkey error")
            print(f"ERROR: {e}")
            return

        menu = pystray.Menu(
            pystray.MenuItem(f"Model: {config['model_size']} ({config['device']})", None, enabled=False),
            pystray.MenuItem(f"Hotkey: {config['hotkey']}", None, enabled=False),
            pystray.MenuItem("Quit", self._quit),
        )
        self.tray_icon = pystray.Icon(
            "whisperkey", self._make_icon_image(IDLE_COLOR), "WhisperKey", menu
        )
        self.tray_icon.run()  # blocks until Quit is clicked
        listener.stop()


def _selftest(wav_path):
    """Load the model and transcribe a 16kHz mono wav, then exit.

    A packaging sanity check: exercises the full CTranslate2 + onnxruntime VAD
    inference path inside the frozen .exe without needing a microphone.
    Usage: WhisperKey.exe --selftest path\\to\\audio.wav
    """
    import wave

    import numpy as np

    with wave.open(wav_path, "rb") as wf:
        assert wf.getframerate() == 16000 and wf.getnchannels() == 1, \
            "self-test expects a 16kHz mono wav"
        frames = wf.readframes(wf.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

    try:
        t = Transcriber()
    except ModelLoadError as e:
        log.error("SELFTEST FAILED (model load): %s", e)
        print(f"SELFTEST FAILED (model load): {e}")
        return 1
    text = t.transcribe(audio)
    # Log as well as print so the self-test is usable on the --windowed build
    # (which has no console); check whisperkey.log for the result.
    log.info("SELFTEST TRANSCRIPT: %r", text)
    log.info("SELFTEST OK" if text else "SELFTEST WARNING: empty transcript")
    print(f"SELFTEST TRANSCRIPT: {text!r}")
    print("SELFTEST OK" if text else "SELFTEST WARNING: empty transcript")
    return 0


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        raise SystemExit(_selftest(sys.argv[2]))

    if len(sys.argv) >= 2 and sys.argv[1] == "--overlay-demo":
        # Packaging check for the overlay (esp. tkinter in the frozen build).
        import time
        ov = Overlay()
        ov.start()
        time.sleep(0.5)
        ov.show_recording()
        time.sleep(3)
        ov.show_transcribing()
        time.sleep(2)
        ov.hide()
        time.sleep(1)
        raise SystemExit(0)

    app = WhisperKeyApp()
    app.run()
