# build-full.ps1 — Windows build script for the Ganesh **full** installer.
#
# The full variant pre-bundles the three required model weight files
# (whisper base, piper default voice, embedding model) into dist\models\
# so the application can run offline on first launch.
#
# Models are NOT downloaded during this build. They must be pre-downloaded
# into the directory pointed to by GANESH_MODELS_SRC (default:
# backend\prebuilt_models\). Run the model_manager manually before
# invoking this script.
#
# Usage:
#   scripts\build-full.ps1 [-SkipTauri]
#
# Environment:
#   $env:GANESH_MODELS_SRC    — path to pre-downloaded models (default: backend\prebuilt_models)
#   $env:GANESH_SKIP_TAURI=1  — skip the Tauri bundling step (PyInstaller only).
[CmdletBinding()]
param(
    [switch]$SkipTauri
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $RootDir "backend"
$ModelsSrc = if ($env:GANESH_MODELS_SRC) { $env:GANESH_MODELS_SRC } else { Join-Path $BackendDir "prebuilt_models" }

if ($env:GANESH_SKIP_TAURI -eq "1") { $SkipTauri = $true }

Write-Host "============================================================"
Write-Host "  Ganesh - Full Installer Build (Windows)"
Write-Host "============================================================"

# --- 1. Verify pre-bundled models exist -------------------------------------
Write-Host "[1/4] Verifying pre-bundled models in: $ModelsSrc"
$RequiredModels = @("stt.bin", "tts.onnx", "embeddings.bin")
$Missing = @()
foreach ($model in $RequiredModels) {
    if (-not (Test-Path (Join-Path $ModelsSrc $model))) {
        $Missing += $model
    }
}
if ($Missing.Count -gt 0) {
    Write-Error "Missing pre-bundled models: $($Missing -join ', '). Place them in $ModelsSrc before building. The full variant must NOT download models during build."
    exit 3
}
Write-Host "  All 3 models present."

# --- 2. Copy models to dist\models\ (before PyInstaller bundles them) --------
Write-Host "[2/4] Copying models to dist\models\..."
$DistModelsDir = Join-Path $BackendDir "dist\models"
New-Item -ItemType Directory -Force -Path $DistModelsDir | Out-Null
foreach ($model in $RequiredModels) {
    Copy-Item (Join-Path $ModelsSrc $model) (Join-Path $DistModelsDir $model) -Force
}

# --- 3. PyInstaller (full spec, bundles models from GANESH_MODELS_SRC) ------
Set-Location $BackendDir
$env:GANESH_MODELS_SRC = $ModelsSrc
Write-Host "[3/4] Building PyInstaller sidecar (full, with models)..."
pyinstaller pyinstaller-full.spec --noconfirm
if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller build failed"; exit 1 }

# --- 4. Tauri bundling ------------------------------------------------------
if ($SkipTauri) {
    Write-Host "[4/4] Skipping Tauri build (-SkipTauri)"
    exit 0
}

Write-Host "[4/4] Building Tauri app (full)..."
Set-Location $RootDir
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    Write-Error "cargo not found. Install Rust from https://rustup.rs/"
    exit 2
}
cargo tauri build
if ($LASTEXITCODE -ne 0) { Write-Error "Tauri build failed"; exit 2 }

Write-Host "============================================================"
Write-Host "  Full build complete."
Write-Host "  Artifacts: src-tauri\target\release\bundle\"
Write-Host "  Bundled models: dist\models\"
Write-Host "============================================================"
