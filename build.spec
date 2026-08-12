# PyInstaller spec for WhisperKey.
#
# Build:   pyinstaller build.spec --noconfirm
# Output:  dist/WhisperKey.exe   (--onefile --windowed)
#
# Bundles the native libs that don't get picked up automatically:
#   - faster_whisper's Silero VAD onnx asset (vad_filter=True needs it)
#   - CTranslate2 native libs (ctranslate2.dll, its bundled cudnn, libiomp5md)
#   - onnxruntime (VAD backend)
#   - sounddevice's PortAudio DLL
#   - the NVIDIA CUDA runtime DLLs (cuBLAS/cuDNN/nvrtc) laid out as
#     nvidia/<pkg>/bin so transcriber._register_cuda_dll_dirs() finds them
#     under sys._MEIPASS at runtime.

import glob
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = []
binaries = []
hiddenimports = ["tkinter"]  # lazily imported in overlay.py; ensure it's bundled

# Collect the packages with native libs / data files wholesale.
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "sounddevice"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# sounddevice's PortAudio DLL lives in the _sounddevice_data package.
datas += collect_data_files("_sounddevice_data")

# Bundle the NVIDIA CUDA DLLs, preserving the nvidia/<pkg>/bin layout the
# runtime DLL-path shim expects (sys._MEIPASS/nvidia/<pkg>/bin).
try:
    import nvidia
    for root in list(nvidia.__path__):
        for pkg in ("cublas", "cudnn", "cuda_nvrtc"):
            bin_dir = os.path.join(root, pkg, "bin")
            for dll in glob.glob(os.path.join(bin_dir, "*.dll")):
                binaries.append((dll, os.path.join("nvidia", pkg, "bin")))
except ImportError:
    pass  # CPU-only build

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# --- Fix mismatched VC++ runtime DLLs -------------------------------------
# numpy ships an OLD vendored msvcp140.dll (14.16) that PyInstaller bundles;
# paired with the 14.51 MSVCP140_1.dll it causes an access-violation crash in
# MSVCP140.dll under CTranslate2/onnxruntime. Drop every bundled copy and use
# the single consistent set from System32.
_RUNTIME_DLLS = {
    "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
    "vcruntime140.dll", "vcruntime140_1.dll", "concrt140.dll",
}
a.binaries = [b for b in a.binaries if os.path.basename(b[0]).lower() not in _RUNTIME_DLLS]
_sys32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
for _name in _RUNTIME_DLLS:
    _p = os.path.join(_sys32, _name)
    if os.path.isfile(_p):
        a.binaries.append((_name, _p, "BINARY"))
# --------------------------------------------------------------------------

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="WhisperKey",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,        # --windowed
    disable_windowed_traceback=False,
)
