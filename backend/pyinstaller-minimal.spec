# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Ganesh **minimal** installer variant.

Build:
    cd backend
    pyinstaller pyinstaller-minimal.spec --noconfirm

The minimal variant ships the backend sidecar **without** any pre-bundled
model files. On first run the application downloads the required models
(whisper base, piper default voice, embedding model) via the first-run
model download flow (see ``ganesh_backend.services.model_manager``).

The frozen binary is written to ``dist/ganesh-backend`` (or
``dist/ganesh-backend.exe`` on Windows). Tauri bundles this binary as a
sidecar (see ``src-tauri/tauri.conf.json`` -> ``bundle.externalBin``).

This spec is intentionally a strict subset of ``pyinstaller-full.spec``:
it collects the same native Python runtimes (pydantic, uvicorn, piper,
faster-whisper, ...) but **never** adds ``.onnx`` / ``.bin`` model weight
files to ``datas``. The ``MINIMAL_EXCLUDES`` tuple documents the model
file extensions that must not appear in the bundle.
"""
from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

block_cipher = None

# --- Model file exclusions --------------------------------------------------
# The minimal variant must NOT bundle any model weight files. These
# extensions are the ones used by faster-whisper (CTranslate2 ``.bin``),
# piper (``.onnx``) and the embedding model (``.bin`` / ``.onnx``).
# They are documented here for the test suite (``test_installer_variants``)
# which parses this spec to assert no model datas are present.
MINIMAL_EXCLUDES = (".onnx", ".bin")

# --- Native dependency collection -------------------------------------------
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
import os

_backend_root = os.path.dirname(os.path.abspath(SPEC))
_config_templates = os.path.join(_backend_root, "config_templates")
if os.path.isdir(_config_templates):
    datas += [(_config_templates, "config_templates")]

# --- Native runtime collection (NO model weights) ---------------------------
# piper-tts (ONNX runtime native) — collect the Python package + native
# libs, but NOT any ``.onnx`` voice model files.
_tmp_datas, _tmp_bins, _tmp_hidden = collect_all("piper")
datas += _tmp_datas
binaries += _tmp_bins
hiddenimports += _tmp_hidden
binaries += collect_dynamic_libs("onnxruntime")

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

# vaderSentiment (pure-Python lexicon sentiment for emotion detection, Task 34).
_tmp_datas, _tmp_bins, _tmp_hidden = collect_all("vaderSentiment")
datas += _tmp_datas
binaries += _tmp_bins
hiddenimports += _tmp_hidden

# --- Strip any accidentally-collected model weight files --------------------
# ``collect_all`` may pull in test fixtures or example model files shipped
# inside a package's data directory. Filter them out to honour the minimal
# contract: NO ``.onnx`` / ``.bin`` files in the bundle.
def _is_model_weight(path: str) -> bool:
    return path.lower().endswith(MINIMAL_EXCLUDES)


datas = [(src, dst) for src, dst in datas if not _is_model_weight(src)]
binaries = [(src, dst) for src, dst in binaries if not _is_model_weight(src)]

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
