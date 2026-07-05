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

## System Dependencies

### Linux (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install -y libgtk-3-dev libwebkit2gtk-4.0-dev libayatana-appindicator3-dev librsvg2-dev
```

### Windows

- WebView2
- Rust (MSVC)
