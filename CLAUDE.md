# CLAUDE.md — WhisperKey

Guidance for AI assistants working in this repo.

## Attribution (important)

Do **not** add Claude / AI as a co-author in commits or PRs. No
`Co-Authored-By: Claude ...` trailer and no `Claude-Session:` trailer. Write
normal commit messages authored as the repo owner. (It's fine that AI helped
write the code — the owner just doesn't want it credited as a formal
co-author in the public git history.)

## What this is

WhisperKey: a local, no-API-key push-to-talk dictation app for Windows. Hold a
hotkey (default F9), speak, release — the transcript is pasted into the focused
app. Transcription runs locally on an NVIDIA GPU via faster-whisper
(CTranslate2). A tray icon and a small on-screen overlay show status.

## Environment / how to run

This dev machine is WSL2 Linux, but WhisperKey is a **Windows** app — it must be
built and run with **Windows Python**, invoked from WSL as
`venv/Scripts/python.exe` (create the venv with
`"/mnt/c/Program Files/Python312/python.exe" -m venv venv`). The WSL Linux
interpreter cannot do the audio/hotkey/clipboard/tray or build the `.exe`.

- Run from source: `venv/Scripts/python.exe main.py`
- Inference sanity check (no mic needed): `... main.py --selftest test.wav`
- Overlay check: `... main.py --overlay-demo`
- Build: `venv/Scripts/pyinstaller.exe build.spec --noconfirm` → `dist/WhisperKey.exe`
  (`build_debug.spec` = console + onedir for tracebacks)
- Logs: `%LOCALAPPDATA%\WhisperKey\whisperkey.log`

## Non-obvious packaging fixes (don't regress these)

- `transcriber.py` preloads the bundled CUDA DLLs by absolute path
  (`ctypes.WinDLL`) — PyInstaller's bootloader drops PATH from the DLL search,
  so this is what lets CTranslate2 find cuBLAS/cuDNN in the frozen `.exe`.
- `build*.spec` strip all VC++ runtime DLLs and re-add the consistent set from
  System32 — numpy vendors an old `msvcp140.dll` that otherwise crashes the exe.
- The overlay is a non-focus-stealing window (`WS_EX_NOACTIVATE`) so it can't
  hijack focus and misdirect the paste.

## Module map

`main.py` (wiring + tray + CLI hooks) · `config.py` (settings + settings.json) ·
`audio_capture.py` (mic → 16kHz mono) · `transcriber.py` (faster-whisper +
CUDA shim) · `injector.py` (clipboard paste) · `hotkey_listener.py` (global
hotkey) · `overlay.py` (on-screen indicator) · `app_logging.py` (file logging).
