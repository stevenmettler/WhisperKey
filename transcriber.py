"""
Thin wrapper around faster-whisper. Keeping this interface narrow
(load once, transcribe(audio) -> str) so the backend can be swapped
for whisper.cpp later without touching the rest of the app.

CUDA note: CTranslate2 (the faster-whisper backend) needs cuBLAS + cuDNN
DLLs to load the CUDA runtime. We ship those as the nvidia-cublas-cu12 /
nvidia-cudnn-cu12 pip wheels; _register_cuda_dll_dirs() adds their bin
folders to the Windows DLL search path so the user doesn't have to edit
PATH. Without this you get the classic "Could not load library
cudnn_ops64_9.dll" failure at model load.
"""

import ctypes
import glob
import os
import sys

import numpy as np

from app_logging import log
from config import config


class ModelLoadError(RuntimeError):
    """Raised when the Whisper model can't be loaded (download or CUDA libs)."""


def _nvidia_roots():
    """Directories that may contain the nvidia/<pkg>/bin CUDA DLL folders."""
    roots = []
    # Primary: wherever the installed `nvidia` namespace package lives.
    try:
        import nvidia
        roots.extend(list(getattr(nvidia, "__path__", [])))
    except Exception:
        pass
    # When frozen by PyInstaller, DLLs land under _MEIPASS/nvidia.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(os.path.join(meipass, "nvidia"))
    return roots


def _preload_dlls(paths):
    """Load each DLL by absolute path so later LoadLibrary(by-name) calls from
    CTranslate2 resolve to these already-loaded modules.

    This is what makes the CUDA libs work in a PyInstaller build: the frozen
    bootloader calls SetDefaultDllDirectories(), which drops PATH from the DLL
    search order, so editing PATH (or even add_dll_directory in some cases) is
    not enough for CTranslate2's runtime-by-name loads. Preloading by full path
    sidesteps the search entirely. We make several passes so inter-dependencies
    (e.g. cudnn_ops -> cudnn_graph, cudnn_cnn -> cublas) resolve regardless of
    load order.
    """
    remaining = list(dict.fromkeys(paths))  # de-dup, preserve order
    loaded = 0
    for _ in range(len(remaining) + 1):
        if not remaining:
            break
        progressed = False
        still = []
        for p in remaining:
            try:
                ctypes.WinDLL(p)
                loaded += 1
                progressed = True
            except OSError:
                still.append(p)  # deps not loaded yet; retry next pass
        remaining = still
        if not progressed:
            break
    if remaining:
        log.warning(
            "could not preload %d CUDA DLL(s): %s",
            len(remaining), [os.path.basename(p) for p in remaining],
        )
    log.debug("preloaded %d CUDA DLL(s)", loaded)


def _register_cuda_dll_dirs():
    """Make the bundled nvidia-*-cu12 CUDA DLLs loadable by CTranslate2."""
    if os.name != "nt":
        return
    bin_dirs = []
    for root in _nvidia_roots():
        if not os.path.isdir(root):
            continue
        for pkg in ("cublas", "cudnn", "cuda_nvrtc"):
            bin_dir = os.path.join(root, pkg, "bin")
            if os.path.isdir(bin_dir):
                bin_dirs.append(bin_dir)
    bin_dirs = list(dict.fromkeys(bin_dirs))  # de-dup

    # Add dirs to the loader search (helps the non-frozen case and dependent
    # resolution) ...
    for bin_dir in bin_dirs:
        try:
            os.add_dll_directory(bin_dir)
        except OSError as e:
            log.warning("could not add DLL dir %s: %s", bin_dir, e)
    if bin_dirs:
        os.environ["PATH"] = os.pathsep.join(bin_dirs) + os.pathsep + os.environ.get("PATH", "")

    # ... but the robust part (esp. under PyInstaller) is explicit preloading.
    dlls = []
    for bin_dir in bin_dirs:
        dlls.extend(glob.glob(os.path.join(bin_dir, "*.dll")))
    _preload_dlls(dlls)
    log.debug("registered %d CUDA DLL dir(s)", len(bin_dirs))


class Transcriber:
    def __init__(self, model_size=None, device=None, compute_type=None):
        model_size = model_size or config["model_size"]
        device = device or config["device"]
        compute_type = compute_type or config["compute_type"]

        if device == "cuda":
            _register_cuda_dll_dirs()

        log.info(
            "loading model '%s' (device=%s, compute_type=%s)...",
            model_size, device, compute_type,
        )
        # Imported here (not at module top) so the DLL dirs above are already
        # registered before CTranslate2's native libs get pulled in.
        from faster_whisper import WhisperModel

        try:
            # First call downloads the model from Hugging Face and caches it
            # locally (~/.cache/huggingface). Subsequent loads are instant.
            self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        except Exception as e:
            raise self._explain_load_failure(e, device) from e
        log.info("model loaded.")

    @staticmethod
    def _explain_load_failure(e: Exception, device: str) -> ModelLoadError:
        msg = str(e)
        low = msg.lower()
        if device == "cuda" and ("cudnn" in low or "cublas" in low or "cuda" in low
                                 or "library" in low):
            hint = (
                "CUDA/cuDNN libraries failed to load. Confirm nvidia-cublas-cu12 "
                "and nvidia-cudnn-cu12 are installed in this environment, or set "
                '"device": "cpu" in settings.json to run on CPU.'
            )
        elif any(k in low for k in ("connection", "download", "http", "resolve",
                                    "network", "timeout", "huggingface")):
            hint = (
                "Model download failed. Check your internet connection; the model "
                "is fetched from Hugging Face on first run."
            )
        else:
            hint = "Model failed to load."
        log.error("%s Underlying error: %s", hint, msg)
        return ModelLoadError(f"{hint} ({e.__class__.__name__}: {msg})")

    def transcribe(self, audio: np.ndarray, language: str = None) -> str:
        """
        audio: float32 numpy array, mono, 16kHz (matches config['sample_rate'])
        Returns the transcribed text as a single string.
        """
        language = language or config["language"]

        segments, info = self.model.transcribe(
            audio,
            language=language,
            beam_size=5,
            vad_filter=True,  # trims silence, reduces hallucinated text on empty audio
            # Priming prompt biases the model toward proper punctuation/casing.
            initial_prompt=config.get("initial_prompt") or None,
        )

        text = " ".join(segment.text.strip() for segment in segments)
        return text.strip()


if __name__ == "__main__":
    # Quick manual test: transcribe a .wav file from the command line.
    # Usage: python transcriber.py path/to/audio.wav
    import wave

    if len(sys.argv) < 2:
        print("Usage: python transcriber.py <path_to_wav_file>")
        sys.exit(1)

    wav_path = sys.argv[1]

    with wave.open(wav_path, "rb") as wf:
        assert wf.getframerate() == 16000, "Expected 16kHz mono wav for this quick test"
        assert wf.getnchannels() == 1, "Expected mono audio for this quick test"
        frames = wf.readframes(wf.getnframes())
        audio_np = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

    try:
        transcriber = Transcriber()
    except ModelLoadError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    result = transcriber.transcribe(audio_np)
    print("\nTranscript:")
    print(result)
