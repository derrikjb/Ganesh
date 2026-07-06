# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Ganesh **full** installer variant.

Build:
    cd backend
    pyinstaller pyinstaller-full.spec --noconfirm

The full variant pre-bundles the three required model weight files into
``dist/models/`` so the application can run offline on first launch
without triggering the first-run download flow (Task 22).

Pre-bundled models (must be present before building):
    - ``stt.bin``    — faster-whisper base model (CTranslate2 format)
    - ``tts.onnx``   — piper default voice (ONNX format)
    - ``embeddings.bin`` — sentence embeddings (all-MiniLM-L6-v2)

The models are read from the directory pointed to by the
``GANESH_MODELS_SRC`` environment variable (default: ``./prebuilt_models``
relative to the spec file). The build scripts (``scripts/build-full.sh``
and ``scripts/build-full.ps1``) are responsible for placing the
pre-downloaded models there before invoking PyInstaller.

.. note::
    The full variant does NOT download models during the build. The
    models must be pre-downloaded (e.g. via a CI cache step or a manual
    ``python -m ganesh_backend.services.model_manager`` run) before
    invoking this spec.
"""
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

block_cipher = None

# --- Model bundle configuration ---------------------------------------------
# Extensions considered "model weight" files for the full variant.
MODEL_EXTENSIONS = (".onnx", ".bin")

# Source directory for pre-downloaded models. Override with the
# ``GANESH_MODELS_SRC`` environment variable.
_backend_root = os.path.dirname(os.path.abspath(SPEC))
_models_src = os.environ.get("GANESH_MODELS_SRC") or os.path.join(
    _backend_root, "prebuilt_models"
)

# Expected model files (name -> description). These are the files the
# full variant bundles into ``dist/models/``.
BUNDLED_MODELS = {
    "stt.bin": "faster-whisper base model (CTranslate2)",
    "tts.onnx": "piper default voice (ONNX)",
    "embeddings.bin": "sentence embeddings (all-MiniLM-L6-v2)",
}

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
_config_templates = os.path.join(_backend_root, "config_templates")
if os.path.isdir(_config_templates):
    datas += [(_config_templates, "config_templates")]

# --- Native runtime collection ----------------------------------------------
# piper-tts (ONNX runtime native)
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

# --- Pre-bundled model weights (full variant only) --------------------------
# Add each pre-downloaded model file to ``datas`` with destination
# ``models/`` so they end up at ``dist/models/<filename>`` in the final
# bundle. Missing models are warned but do NOT fail the build — the
# first-run download flow will fetch them at runtime if absent.
import warnings  # noqa: E402

_bundled_any = False
if os.path.isdir(_models_src):
    for _name, _desc in BUNDLED_MODELS.items():
        _model_path = os.path.join(_models_src, _name)
        if os.path.isfile(_model_path):
            datas += [(_model_path, "models")]
            _bundled_any = True
        else:
            warnings.warn(
                f"Model file '{_name}' ({_desc}) not found in "
                f"'{_models_src}'. The full installer will not pre-bundle "
                f"this model; first-run download will be required."
            )
else:
    warnings.warn(
        f"Models source directory '{_models_src}' does not exist. "
        f"The full installer will not pre-bundle any models; first-run "
        f"download will be required for all three."
    )

# Expose the bundled-models manifest for the test suite to introspect.
BUNDLED_MODELS_PRESENT = _bundled_any

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
