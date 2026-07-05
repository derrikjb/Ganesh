# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Ganesh backend sidecar (onefile).

Build:
    cd backend
    pyinstaller pyinstaller.spec

The frozen binary is written to ``dist/ganesh-backend`` (or
``dist/ganesh-backend.exe`` on Windows). Tauri bundles this binary as a
sidecar (see ``src-tauri/tauri.conf.json`` -> ``bundle.externalBin``).
"""
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

block_cipher = None

# --- Native dependency collection -------------------------------------------
# Each entry uses PyInstaller's collect helpers to pull in data files, hidden
# imports, and dynamic libraries that static analysis would otherwise miss.
datas = []
binaries = []
hiddenimports = []

# pydantic v2 ships a Rust-compiled core (pydantic-core) that needs its
# shared library bundled.
_tmp_datas, _tmp_bins, _tmp_hidden = collect_all("pydantic")
datas += _tmp_datas
binaries += _tmp_bins
hiddenimports += _tmp_hidden

_tmp_datas, _tmp_bins, _tmp_hidden = collect_all("pydantic_core")
datas += _tmp_datas
binaries += _tmp_bins
hiddenimports += _tmp_hidden

# uvicorn[standard] pulls in httptools / uvloop / watchfiles on platforms that
# support them; collect their native libs.
_tmp_datas, _tmp_bins, _tmp_hidden = collect_all("uvicorn")
datas += _tmp_datas
binaries += _tmp_bins
hiddenimports += _tmp_hidden

binaries += collect_dynamic_libs("pydantic_core")
binaries += collect_dynamic_libs("uvicorn")

# keyring uses platform-specific backends (SecretStorage on Linux, Windows
# Credential Manager on Windows). collect_all ensures the backends ship.
_tmp_datas, _tmp_bins, _tmp_hidden = collect_all("keyring")
datas += _tmp_datas
binaries += _tmp_bins
hiddenimports += _tmp_hidden

# --- Config templates (data files) ------------------------------------------
# Ship YAML config templates so the sidecar can write a default config on
# first run. Adjust the path as the config layout matures.
import os

_backend_root = os.path.dirname(os.path.abspath(SPEC))
_config_templates = os.path.join(_backend_root, "config_templates")
if os.path.isdir(_config_templates):
    datas += [(_config_templates, "config_templates")]

# --- Future native deps (Wave 2+) ------------------------------------------
# Uncomment as each dependency is added to pyproject.toml.
#
# piper-tts (ONNX runtime native)
_tmp_datas, _tmp_bins, _tmp_hidden = collect_all("piper")
datas += _tmp_datas
binaries += _tmp_bins
hiddenimports += _tmp_hidden
binaries += collect_dynamic_libs("onnxruntime")
#
# # sounddevice (PortAudio C library)
# _tmp_datas, _tmp_bins, _tmp_hidden = collect_all("sounddevice")
# datas += _tmp_datas; binaries += _tmp_bins; hiddenimports += _tmp_hidden
# binaries += collect_dynamic_libs("sounddevice")

# faster-whisper (CTranslate2 native runtime). Also collect the transitive
# native libs from ctranslate2 (the C++ inference engine) and onnxruntime
# (used by faster-whisper for VAD). PyAV (`av`) brings its own ffmpeg libs
# which collect_dynamic_libs will pull in.
_tmp_datas, _tmp_bins, _tmp_hidden = collect_all("faster_whisper")
datas += _tmp_datas
binaries += _tmp_bins
hiddenimports += _tmp_hidden

binaries += collect_dynamic_libs("ctranslate2")
binaries += collect_dynamic_libs("onnxruntime")
binaries += collect_dynamic_libs("av")

a = Analysis(
    ["main.py"],
    pathex=[_backend_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ganesh-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # sidecar must keep stdout/stderr for Tauri to read PORT: line
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
