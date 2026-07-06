# build-minimal.ps1 — Windows build script for the Ganesh **minimal** installer.
#
# The minimal variant ships the backend sidecar WITHOUT pre-bundled model
# files. On first run the application downloads the required models via
# the first-run model download flow (Task 22).
#
# Usage:
#   scripts\build-minimal.ps1 [-SkipTauri]
#
# Environment:
#   $env:GANESH_SKIP_TAURI=1  — skip the Tauri bundling step (PyInstaller only).
[CmdletBinding()]
param(
    [switch]$SkipTauri
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path $RootDir "backend"

if ($env:GANESH_SKIP_TAURI -eq "1") { $SkipTauri = $true }

Write-Host "============================================================"
Write-Host "  Ganesh - Minimal Installer Build (Windows)"
Write-Host "============================================================"

# --- 1. PyInstaller (minimal spec, no models) -------------------------------
Set-Location $BackendDir
Write-Host "[1/3] Building PyInstaller sidecar (minimal, no models)..."
pyinstaller pyinstaller-minimal.spec --noconfirm
if ($LASTEXITCODE -ne 0) { Write-Error "PyInstaller build failed"; exit 1 }

# --- 2. Smoke test the frozen binary ----------------------------------------
Write-Host "[2/3] Verifying frozen binary (--check-imports)..."
$exePath = Join-Path $BackendDir "dist\ganesh-backend.exe"
if (Test-Path $exePath) {
    & $exePath --check-imports
    if ($LASTEXITCODE -ne 0) { Write-Error "Frozen binary --check-imports failed"; exit 1 }
} else {
    Write-Error "dist\ganesh-backend.exe not found"
    exit 1
}

# --- 3. Tauri bundling ------------------------------------------------------
if ($SkipTauri) {
    Write-Host "[3/3] Skipping Tauri build (-SkipTauri)"
    exit 0
}

Write-Host "[3/3] Building Tauri app (minimal)..."
Set-Location $RootDir
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    Write-Error "cargo not found. Install Rust from https://rustup.rs/"
    exit 2
}
cargo tauri build
if ($LASTEXITCODE -ne 0) { Write-Error "Tauri build failed"; exit 2 }

Write-Host "============================================================"
Write-Host "  Minimal build complete."
Write-Host "  Artifacts: src-tauri\target\release\bundle\"
Write-Host "============================================================"
