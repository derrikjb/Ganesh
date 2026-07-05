# Native Dependencies Registry

This document tracks Python dependencies with native components (C/C++/Rust/etc.) and their handling in the PyInstaller frozen binary.

## Registry

| Dependency | Native? | PyInstaller Handling | Notes |
|------------|---------|----------------------|-------|
| `fastapi` | No | Pure Python | Standard import |
| `uvicorn` | No | Pure Python | Standard import |
| `litellm` | No | Pure Python | Standard import |
| `pydantic` | Yes | `collect_dynamic_libs` | Rust-backed in v2 |
| `keyring` | Yes | Platform-specific | Uses OS-level secret stores |

## Future Dependencies (Wave 2+)

- `faster-whisper` (Native: CTranslate2)
- `piper-tts` (Native: Piper)
- `lancedb` (Native: Rust)
- `sounddevice` (Native: PortAudio)

## Verification

The frozen binary supports a `--check-imports` flag to verify all native dependencies are correctly bundled and importable in the frozen environment.

```bash
./ganesh-backend --check-imports
```

## System Dependencies

### Linux (Ubuntu/Debian)

```bash
sudo apt-get update
sudo apt-get install -y libgtk-3-dev libwebkit2gtk-4.0-dev libayatana-appindicator3-dev librsvg2-dev
```

### Windows

- WebView2
- Rust (MSVC)
