# Native Dependencies Registry

This document tracks Python dependencies with native components (C/C++/Rust/etc.)
and their handling in the PyInstaller frozen binary (`backend/pyinstaller.spec`).

## Registry

| Dependency | Native? | Import name | PyInstaller Handling | Notes |
|------------|---------|-------------|----------------------|-------|
| `fastapi` | No | `fastapi` | Pure Python | Standard import |
| `uvicorn[standard]` | Partial | `uvicorn` | `collect_all("uvicorn")` | Pulls httptools/uvloop/watchfiles native libs on supported platforms |
| `litellm` | No | `litellm` | Pure Python | Standard import |
| `pydantic` | Yes (Rust) | `pydantic` | `collect_all("pydantic")` | pydantic v2 core is Rust-compiled |
| `pydantic-core` | Yes (Rust) | `pydantic_core` | `collect_all` + `collect_dynamic_libs` | Shared lib `libpydantic_core` |
| `keyring` | Yes | `keyring` | `collect_all("keyring")` | Platform-specific backends (SecretStorage on Linux, Windows Credential Manager) |
| `pyyaml` | No | `yaml` | Pure Python | Note: import name is `yaml`, not `pyyaml` |
| `piper-tts` | Yes (ONNX Runtime, C++) | `piper` | `collect_all("piper")` + `collect_dynamic_libs("onnxruntime")` | Note: package name is `piper-tts`, import name is `piper`. ONNX Runtime ships native shared libs. |
| `faster-whisper` | Yes (C++) | `faster_whisper` | `collect_all("faster_whisper")` + `collect_dynamic_libs("ctranslate2")` | CTranslate2 native runtime; pulls onnxruntime + av (PyAV) as transitive native deps |
| `vaderSentiment` | No | `vaderSentiment` | Pure Python | Lexicon + rule-based sentiment for emotion detection (Task 34). Package and import name both `vaderSentiment`. |

## `--check-imports` Verification

The sidecar exposes a `--check-imports` CLI flag that imports every entry in
`main.NATIVE_DEPS` and exits `0` on success or `1` on failure. This is the
frozen-binary smoke test — run it after every PyInstaller build.

```bash
./ganesh-backend --check-imports
# stdout: All native imports OK
```

The registry lives in `backend/main.py` (`NATIVE_DEPS` tuple). Add new native
deps there and to the spec file in the same change.

## Future Dependencies (Wave 2+)

These will be added to the registry and the PyInstaller spec as they land:

| Dependency | Native runtime | Import name |
|------------|----------------|-------------|
| `sounddevice` | PortAudio (C) | `sounddevice` |

> `faster-whisper`, `lancedb`, and `piper-tts` have graduated from this list —
> they are now installed, registered in `main.NATIVE_DEPS`, and collected in
> `pyinstaller.spec`.

The `pyinstaller.spec` already contains commented-out `collect_all` /
`collect_dynamic_libs` blocks for each of these — uncomment when the dep is added.

## Installer Variants (Task 38)

Ganesh ships two installer variants, each driven by a dedicated PyInstaller
spec and a pair of build scripts (Linux `.sh` + Windows `.ps1`):

| Variant | Spec | Models bundled | First-run download |
|---------|------|----------------|--------------------|
| **minimal** | `backend/pyinstaller-minimal.spec` | None | Required (Task 22) |
| **full** | `backend/pyinstaller-full.spec` | `stt.bin`, `tts.onnx`, `embeddings.bin` in `dist/models/` | Optional (offline-capable) |

### Build scripts

| Script | Variant | Platform |
|--------|---------|----------|
| `scripts/build-minimal.sh` | minimal | Linux |
| `scripts/build-minimal.ps1` | minimal | Windows |
| `scripts/build-full.sh` | full | Linux |
| `scripts/build-full.ps1` | full | Windows |

### Pre-bundled models (full variant)

The full variant does **NOT** download models during the build. Models must
be pre-downloaded into the directory pointed to by `GANESH_MODELS_SRC`
(default: `backend/prebuilt_models/`) before invoking the build script.

Expected files:

| File | Description |
|------|-------------|
| `stt.bin` | faster-whisper base model (CTranslate2 format) |
| `tts.onnx` | piper default voice (ONNX format) |
| `embeddings.bin` | sentence embeddings (all-MiniLM-L6-v2) |

### CI

`.github/workflows/ci.yml` defines a `build-variants` job with an
`OS × variant` matrix (`windows-latest`, `ubuntu-latest` × `minimal`, `full`).
`.github/workflows/build.yml` (tag-triggered release builds) uses the same
matrix and uploads minimal/full artifacts separately. No macOS builds.

## Installer Variants (Task 38)

Ganesh ships two installer variants, each driven by its own PyInstaller spec:

| Variant | Spec file | Models bundled | First-run behavior |
|---------|-----------|----------------|--------------------|
| **Minimal** | `backend/pyinstaller-minimal.spec` | None | Downloads models on first run (Task 22) |
| **Full** | `backend/pyinstaller-full.spec` | `stt.bin`, `tts.onnx`, `embeddings.bin` in `dist/models/` | Runs offline immediately |

### Minimal spec

The minimal spec collects the same native Python runtimes (pydantic, uvicorn,
piper, faster-whisper, ...) as the full spec but **never** adds `.onnx` /
`.bin` model weight files to `datas`. A `MINIMAL_EXCLUDES` tuple and an
`_is_model_weight` filter strip any model files that `collect_all()` might
accidentally pull in from package data directories.

### Full spec

The full spec reads pre-downloaded model files from the directory pointed to
by `GANESH_MODELS_SRC` (default: `backend/prebuilt_models/`) and adds them
to `datas` with destination `models/`. The build scripts
(`scripts/build-full.sh` / `scripts/build-full.ps1`) verify the three required
model files exist before invoking PyInstaller and copy them to
`backend/dist/models/` for Tauri resource bundling.

**The full variant does NOT download models during the build.** Models must
be pre-downloaded (e.g. via CI cache or a manual `model_manager` run) before
invoking the build script.

### Build scripts

| Script | Platform | Variant |
|--------|----------|---------|
| `scripts/build-minimal.sh` | Linux | Minimal |
| `scripts/build-minimal.ps1` | Windows | Minimal |
| `scripts/build-full.sh` | Linux | Full |
| `scripts/build-full.ps1` | Windows | Full |

### CI (`.github/workflows/build.yml`)

The release workflow defines `build-minimal` and `build-full` jobs, each with
an OS matrix (`windows-latest`, `ubuntu-latest`). The full job caches
pre-bundled models across runs to avoid re-downloading. Artifacts are
uploaded separately as `ganesh-minimal-<os>` and `ganesh-full-<os>`.

No macOS builds (Task 38 constraint).

## System Dependencies

### Linux (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install -y libgtk-3-dev libwebkit2gtk-4.0-dev libayatana-appindicator3-dev librsvg2-dev
```

### Windows

- WebView2
- Rust (MSVC)
