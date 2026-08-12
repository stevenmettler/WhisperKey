# Third-party notices

WhisperKey is MIT-licensed (see `LICENSE`). It builds on other people's work.
This file lists the runtime dependencies and their licenses so you know what
you're distributing if you redistribute WhisperKey or a build of it.

## Python dependencies

| Component | Role | License |
|---|---|---|
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | Whisper inference | MIT |
| [CTranslate2](https://github.com/OpenNMT/CTranslate2) | inference engine (native) | MIT |
| Whisper `*.en` model weights (via SYSTRAN on Hugging Face) | the speech model | MIT |
| [Silero VAD](https://github.com/snakers4/silero-vad) (bundled in faster-whisper) | voice-activity detection | MIT |
| [onnxruntime](https://github.com/microsoft/onnxruntime) | runs the VAD model | MIT |
| [sounddevice](https://github.com/spatialaudio/python-sounddevice) + [PortAudio](https://www.portaudio.com/) | microphone capture | MIT |
| [keyboard](https://github.com/boppreh/keyboard) | global hotkey | MIT |
| [pyperclip](https://github.com/asweigart/pyperclip) | clipboard | BSD-3-Clause |
| [numpy](https://numpy.org/) | arrays | BSD-3-Clause |
| [Pillow](https://python-pillow.org/) | tray icon image | MIT-CMU (HPND) |
| [PyAV](https://github.com/PyAV-Org/PyAV) (pulled in by faster-whisper) | audio decoding | BSD-3-Clause |
| [huggingface-hub](https://github.com/huggingface/huggingface_hub), [tokenizers](https://github.com/huggingface/tokenizers) | model download / tokenization | Apache-2.0 |
| **[pystray](https://github.com/moses-palmer/pystray)** | system tray icon | **LGPL-3.0** |

## Two things to be aware of

**pystray is LGPL-3.0** (everything else above is permissive: MIT / BSD /
Apache / HPND). Depending on an LGPL library from an MIT project is fine —
WhisperKey imports pystray dynamically and doesn't modify it, which is exactly
what the LGPL permits. If you distribute a **bundled build** (e.g. a PyInstaller
`.exe`) the LGPL asks that recipients be able to relink/replace the pystray
component; shipping the source (this repo) satisfies that. If you'd rather avoid
LGPL entirely, pystray is the only thing to swap.

**NVIDIA CUDA libraries** (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`) are
**proprietary**, under NVIDIA's license/EULA — *not* open source. This repo does
**not** contain them; users install them via `pip` themselves, so the source
distribution is unaffected. Only relevant if you decide to distribute a
**prebuilt `.exe`** that bundles those DLLs — then you must follow NVIDIA's
redistribution terms for the CUDA runtime and cuDNN. (WhisperKey ships as source
for this reason.)
