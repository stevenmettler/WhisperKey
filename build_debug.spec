# Debug build: console=True + onedir, so we can SEE crashes that the
# --windowed --onefile build swallows. Output: dist/WhisperKey-debug/WhisperKey-debug.exe
#
# Build: pyinstaller build_debug.spec --noconfirm

import glob
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = []
binaries = []
hiddenimports = ["tkinter"]  # lazily imported in overlay.py; ensure it's bundled

for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "sounddevice"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

datas += collect_data_files("_sounddevice_data")

try:
    import nvidia
    for root in list(nvidia.__path__):
        for pkg in ("cublas", "cudnn", "cuda_nvrtc"):
            bin_dir = os.path.join(root, pkg, "bin")
            for dll in glob.glob(os.path.join(bin_dir, "*.dll")):
                binaries.append((dll, os.path.join("nvidia", pkg, "bin")))
except ImportError:
    pass

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name="WhisperKey-debug",
    debug=False,
    strip=False,
    upx=False,
    console=True,        # <-- see the crash
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="WhisperKey-debug",
)
