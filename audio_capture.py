"""
Records mic audio into an in-memory buffer while active.
Hold-to-record model: start() / stop() are called by the hotkey listener
on key-down / key-up.

Audio is always returned as mono float32 at config['sample_rate'] (16 kHz,
Whisper's native rate). We normally ask PortAudio to capture at 16 kHz
directly (the Windows audio engine resamples for us). If a given device
refuses that rate (can happen with WASAPI/exclusive devices), we fall back
to the device's native rate and resample to 16 kHz ourselves.
"""

import threading

import numpy as np
import sounddevice as sd

from app_logging import log
from config import config

TARGET_RATE = 16000  # Whisper's native rate


class NoInputDeviceError(RuntimeError):
    """Raised when there is no usable microphone / input device."""


def _resample_to_target(audio: np.ndarray, src_rate: int) -> np.ndarray:
    """Linear-interpolation resample of mono float32 audio to TARGET_RATE.

    Only used on the fallback path (device rejected a direct 16 kHz open);
    good enough for speech intelligibility.
    """
    if src_rate == TARGET_RATE or audio.size == 0:
        return audio
    duration = audio.shape[0] / float(src_rate)
    n_out = int(round(duration * TARGET_RATE))
    if n_out <= 0:
        return np.array([], dtype=np.float32)
    src_idx = np.linspace(0.0, audio.shape[0] - 1, n_out)
    out = np.interp(src_idx, np.arange(audio.shape[0]), audio)
    return out.astype(np.float32)


def has_input_device(device=None) -> bool:
    """True if the given (or default) device exposes at least one input channel."""
    try:
        if device is None:
            default_in = sd.default.device[0]
            if default_in is None or default_in < 0:
                return False
            info = sd.query_devices(default_in)
        else:
            info = sd.query_devices(device)
        return int(info.get("max_input_channels", 0)) > 0
    except Exception as e:  # PortAudio may raise if there are no devices at all
        log.error("could not query input devices: %s", e)
        return False


class AudioRecorder:
    def __init__(self, sample_rate=None, device=None):
        self.target_rate = sample_rate or config["sample_rate"]
        self.device = device if device is not None else config["mic_device"]
        self._frames = []
        self._stream = None
        self._capture_rate = self.target_rate  # actual rate the stream opened at
        self._lock = threading.Lock()
        self.recording = False

    def _callback(self, indata, frames, time_info, status):
        if status:
            log.warning("audio stream status: %s", status)
        with self._lock:
            self._frames.append(indata.copy())

    def _open_stream(self, samplerate):
        stream = sd.InputStream(
            samplerate=samplerate,
            channels=1,
            dtype="float32",
            device=self.device,
            callback=self._callback,
        )
        stream.start()
        return stream

    def start(self):
        if self.recording:
            return

        if not has_input_device(self.device):
            raise NoInputDeviceError(
                "No microphone / input device detected. Plug in a mic (or set "
                "'mic_device' in settings.json to a valid input device index) "
                "and try again."
            )

        self._frames = []

        # Try the target rate first; fall back to the device's native rate.
        try:
            self._stream = self._open_stream(self.target_rate)
            self._capture_rate = self.target_rate
        except Exception as e:
            log.warning(
                "could not open input at %d Hz (%s); falling back to device "
                "native rate + resample", self.target_rate, e
            )
            try:
                dev_info = sd.query_devices(
                    self.device if self.device is not None else sd.default.device[0]
                )
                native = int(dev_info["default_samplerate"])
                self._stream = self._open_stream(native)
                self._capture_rate = native
            except Exception as e2:
                raise NoInputDeviceError(
                    f"Failed to open the microphone: {e2}. Check that another "
                    "app isn't holding the device exclusively, or set a "
                    "different 'mic_device' in settings.json."
                ) from e2

        self.recording = True
        log.info("recording started (capture rate %d Hz)", self._capture_rate)

    def stop(self) -> np.ndarray:
        """Stops recording; returns captured audio as mono float32 at TARGET_RATE."""
        if not self.recording:
            return np.array([], dtype=np.float32)

        self.recording = False
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None

        with self._lock:
            if not self._frames:
                log.info("recording stopped (no audio captured)")
                return np.array([], dtype=np.float32)
            audio = np.concatenate(self._frames, axis=0).flatten()

        if self._capture_rate != self.target_rate:
            audio = _resample_to_target(audio, self._capture_rate)

        log.info("recording stopped (%.2fs captured)", len(audio) / self.target_rate)
        return audio

    @staticmethod
    def list_devices():
        """Prints available input devices — useful for picking mic_device in config."""
        print(sd.query_devices())


if __name__ == "__main__":
    # Quick manual test: list devices and report whether a default mic exists.
    AudioRecorder.list_devices()
    print()
    if has_input_device():
        default_in = sd.default.device[0]
        info = sd.query_devices(default_in)
        print(f"Default input device OK: [{default_in}] {info['name']}")
    else:
        print("WARNING: no input device detected.")
