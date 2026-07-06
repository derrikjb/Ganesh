#!/bin/bash
# build-full.sh — Linux build script for the Ganesh **full** installer.
#
# The full variant pre-bundles the three required model weight files
# (whisper base, piper default voice, embedding model) into dist/models/
# so the application can run offline on first launch.
#
# Models are NOT downloaded during this build. They must be pre-downloaded
# into the directory pointed to by GANESH_MODELS_SRC (default:
# backend/prebuilt_models/). Use scripts/fetch-models.sh or run the
# model_manager manually before invoking this script.
#
# Usage:
#   scripts/build-full.sh [--skip-tauri]
#
# Environment:
#   GANESH_MODELS_SRC    — path to pre-downloaded models (default: backend/prebuilt_models)
#   GANESH_SKIP_TAURI=1  — skip the Tauri bundling step (PyInstaller only).
#
# Exit codes:
#   0  — success
#   1  — PyInstaller build failed
#   2  — Tauri build failed
#   3  — pre-bundled models missing
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
SKIP_TAURI="${GANESH_SKIP_TAURI:-0}"
MODELS_SRC="${GANESH_MODELS_SRC:-$BACKEND_DIR/prebuilt_models}"

if [[ "${1:-}" == "--skip-tauri" ]]; then
    SKIP_TAURI=1
fi

echo "============================================================"
echo "  Ganesh — Full Installer Build (Linux)"
echo "============================================================"

# --- 1. Verify pre-bundled models exist -------------------------------------
echo "[1/4] Verifying pre-bundled models in: $MODELS_SRC"
REQUIRED_MODELS=("stt.bin" "tts.onnx" "embeddings.bin")
MISSING=()
for model in "${REQUIRED_MODELS[@]}"; do
    if [[ ! -f "$MODELS_SRC/$model" ]]; then
        MISSING+=("$model")
    fi
done
if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "ERROR: Missing pre-bundled models: ${MISSING[*]}" >&2
    echo "       Place them in $MODELS_SRC before building." >&2
    echo "       The full variant must NOT download models during build." >&2
    exit 3
fi
echo "  All 3 models present."

# --- 2. Copy models to dist/models/ (before PyInstaller bundles them) -------
echo "[2/4] Copying models to dist/models/..."
mkdir -p "$BACKEND_DIR/dist/models"
for model in "${REQUIRED_MODELS[@]}"; do
    cp "$MODELS_SRC/$model" "$BACKEND_DIR/dist/models/$model"
done

# --- 3. PyInstaller (full spec, bundles models from GANESH_MODELS_SRC) ------
cd "$BACKEND_DIR"
export GANESH_MODELS_SRC="$MODELS_SRC"
echo "[3/4] Building PyInstaller sidecar (full, with models)..."
pyinstaller pyinstaller-full.spec --noconfirm

# --- 4. Tauri bundling ------------------------------------------------------
if [[ "$SKIP_TAURI" == "1" ]]; then
    echo "[4/4] Skipping Tauri build (GANESH_SKIP_TAURI=1)"
    exit 0
fi

echo "[4/4] Building Tauri app (full)..."
cd "$ROOT_DIR"
if ! command -v cargo &> /dev/null; then
    echo "ERROR: cargo not found. Install Rust from https://rustup.rs/" >&2
    exit 2
fi
cargo tauri build

echo "============================================================"
echo "  Full build complete."
echo "  Artifacts: src-tauri/target/release/bundle/"
echo "  Bundled models: dist/models/"
echo "============================================================"
