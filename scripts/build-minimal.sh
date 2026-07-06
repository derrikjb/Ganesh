#!/bin/bash
# build-minimal.sh — Linux build script for the Ganesh **minimal** installer.
#
# The minimal variant ships the backend sidecar WITHOUT pre-bundled model
# files. On first run the application downloads the required models via
# the first-run model download flow (Task 22).
#
# Usage:
#   scripts/build-minimal.sh [--skip-tauri]
#
# Environment:
#   GANESH_SKIP_TAURI=1  — skip the Tauri bundling step (PyInstaller only).
#
# Exit codes:
#   0  — success
#   1  — PyInstaller build failed
#   2  — Tauri build failed
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
SKIP_TAURI="${GANESH_SKIP_TAURI:-0}"

if [[ "${1:-}" == "--skip-tauri" ]]; then
    SKIP_TAURI=1
fi

echo "============================================================"
echo "  Ganesh — Minimal Installer Build (Linux)"
echo "============================================================"

# --- 1. PyInstaller (minimal spec, no models) -------------------------------
cd "$BACKEND_DIR"
echo "[1/3] Building PyInstaller sidecar (minimal, no models)..."
pyinstaller pyinstaller-minimal.spec --noconfirm

# --- 2. Smoke test the frozen binary ----------------------------------------
echo "[2/3] Verifying frozen binary (--check-imports)..."
if [[ -x "./dist/ganesh-backend" ]]; then
    ./dist/ganesh-backend --check-imports
else
    echo "ERROR: dist/ganesh-backend not found or not executable" >&2
    exit 1
fi

# --- 3. Tauri bundling ------------------------------------------------------
if [[ "$SKIP_TAURI" == "1" ]]; then
    echo "[3/3] Skipping Tauri build (GANESH_SKIP_TAURI=1)"
    exit 0
fi

echo "[3/3] Building Tauri app (minimal)..."
cd "$ROOT_DIR"
if ! command -v cargo &> /dev/null; then
    echo "ERROR: cargo not found. Install Rust from https://rustup.rs/" >&2
    exit 2
fi
cargo tauri build

echo "============================================================"
echo "  Minimal build complete."
echo "  Artifacts: src-tauri/target/release/bundle/"
echo "============================================================"
