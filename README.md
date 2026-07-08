# Ganesh AI Assistant

[![CI](https://github.com/derrikjb/Ganesh/actions/workflows/ci.yml/badge.svg)](https://github.com/derrikjb/Ganesh/actions/workflows/ci.yml)

Ganesh is a local-first, privacy-focused desktop AI assistant built for Windows and Linux. It keeps your conversations and data on your machine. No cloud required unless you want it.

The app pairs a lightweight Tauri v2 desktop shell with a Python FastAPI sidecar that handles AI logic, voice processing, memory, and task orchestration. Everything runs locally by default. Cloud LLM providers are optional fallbacks.

## Table of Contents

- [What Ganesh Can Do](#what-ganesh-can-do)
- [Screenshots](#screenshots)
- [System Requirements](#system-requirements)
- [Installation](#installation)
- [Development Setup](#development-setup)
- [Usage](#usage)
- [Configuration](#configuration)
- [Building from Source](#building-from-source)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## What Ganesh Can Do

### Core Features

- **Chat and voice I/O**. Type messages or speak to Ganesh. Speech-to-text uses faster-whisper locally with a cloud fallback. Text-to-speech uses Piper locally with a cloud fallback.
- **Dynamic memory**. Ganesh remembers context across sessions using mem0 OSS and LanceDB. You can explicitly add, update, invalidate, or delete memories.
- **Adaptive personality**. A configurable trait matrix shifts based on conversation context. Personality stays bounded so it does not drift endlessly.
- **Sub-agent orchestration**. Spawn background tasks and sub-agents. Query their status, cancel them, or collect results. All task state lives in a local SQLite store.
- **Python plugin system**. Drop plugins into `~/.ganesh/plugins/`. Ganesh loads them dynamically via importlib using a simple manifest file.
- **Multiple user profiles**. Switch between profiles. Share a bridge memory layer across profiles with explicit permission controls.
- **Modular voice visualizer**. Choose from waveform, frequency bars, holographic face, or particle effects. The visualizer is swappable via a plugin interface.
- **In-app document viewer**. Open images, text files, PDFs, and JSON documents inside the app. Annotate them without leaving the conversation.
- **Theme system**. Customize borders, backgrounds, and chat style or color. The app ships with a dark theme only.
- **System tray and global hotkey**. Keep Ganesh running in the background. Summon it with a hotkey from anywhere.
- **Conversation history**. Search, export, or delete past conversations. Export formats include JSON and Markdown.
- **Lifelike behavior**. Ambient idle animations, session continuity greetings, emotional context awareness, proactive suggestions, natural response pacing, and a thinking indicator.
- **Auto-update**. Tauri's updater checks for new releases and installs them automatically.
- **Error recovery**. If the sidecar crashes, Ganesh detects it, shows a reconnecting state, and attempts to restart. Corrupted memory and disk-full conditions are handled gracefully.

### Architecture

- `backend/`: Python FastAPI sidecar. Handles LLM routing, voice, memory, orchestration, and plugins.
- `frontend/`: Vite + React + TypeScript + Tailwind CSS desktop UI.
- `src-tauri/`: Tauri v2 core. Manages the native window, system tray, global hotkey, sidecar lifecycle, and auto-updater.
- `docs/`: Project documentation, including the native dependency registry.
- `scripts/`: Build scripts for minimal and full installer variants.
- `.github/workflows/`: CI/CD pipelines for Windows and Linux.

## Screenshots

> Screenshots will be added as features stabilize. Placeholder paths below.

| Feature | Path |
|---------|------|
| Main chat interface | `docs/screenshots/chat-interface.png` |
| Voice visualizer | `docs/screenshots/voice-visualizer.png` |
| Document viewer | `docs/screenshots/document-viewer.png` |
| Theme customization | `docs/screenshots/theme-settings.png` |
| Plugin manager | `docs/screenshots/plugin-manager.png` |
| System tray menu | `docs/screenshots/system-tray.png` |

## System Requirements

### Supported Platforms

- **Windows 10/11** (64-bit)
- **Linux** (Ubuntu 22.04+, Debian 12+, and derivatives)

macOS is not supported.

### Prerequisites for Development

| Tool | Minimum Version | Purpose |
|------|-----------------|---------|
| Node.js | 20.x | Frontend build and Tauri CLI |
| npm | 10.x | Package management |
| Python | 3.11+ | Backend sidecar |
| Rust | latest stable | Tauri native shell |
| WebView2 | latest | Windows runtime (usually preinstalled) |

### Linux System Dependencies

Before building on Linux, install the following packages:

```bash
sudo apt-get update
sudo apt-get install -y libgtk-3-dev libwebkit2gtk-4.0-dev libayatana-appindicator3-dev librsvg2-dev
```

### Disk Space

- Development: at least 5 GB free
- Runtime: varies by installer variant (minimal downloads models on first run; full bundles them)

## Installation

### Prebuilt Installers

Download the latest release from the [Releases](https://github.com/derrikjb/Ganesh/releases) page.

Two variants are available:

| Variant | Size | Models | Best For |
|---------|------|--------|----------|
| **Minimal** | Smaller | Downloaded on first run | Users with good internet |
| **Full** | Larger | Pre-bundled | Offline use or slow connections |

Windows users receive an `.msi` or `.exe` installer. Linux users receive a `.deb` package or `.AppImage`.

### First Run

1. Install the package for your platform.
2. Launch Ganesh.
3. If you chose the minimal variant, the app downloads voice and embedding models on first run. Progress is shown in the UI. Downloads resume if interrupted.
4. Add your API keys in Settings if you want to use cloud LLM providers. Local providers like Ollama do not need keys.

## Development Setup

### 1. Clone the Repository

```bash
git clone https://github.com/derrikjb/Ganesh.git
cd Ganesh
```

### 2. Run the Environment Preflight

```bash
# Linux
bash scripts/preflight.sh

# Windows
pwsh scripts/preflight.ps1
```

This script checks that Node.js, Python, Rust, and Linux system dependencies are present. It exits with a clear report if anything is missing.

### 3. Install Frontend Dependencies

```bash
cd frontend
npm install
```

### 4. Install Backend Dependencies

```bash
cd backend
pip install -e ".[dev]"
```

This installs the FastAPI sidecar in editable mode with development tools including pytest, mypy, and ruff.

### 5. Verify the Rust Sidecar Builds

```bash
cd src-tauri
cargo check
```

### 6. Start the Development App

From the repository root:

```bash
npm run tauri dev
```

This starts the Vite dev server, launches the Tauri desktop window, and spawns the Python sidecar automatically. The frontend connects to the sidecar on an ephemeral port.

## Usage

### Chat

Open Ganesh and type in the message box. Press Enter to send. Responses stream in real time. Drag and drop files into the chat to open them in the document viewer.

### Voice Input and Output

- **Push-to-talk**: Hold the configured key while speaking.
- **Wake word**: Say the wake phrase to start listening.
- **Voice Activity Detection (VAD)**: Ganesh listens automatically when you speak.

Voice output can be interrupted (barge-in) if you start speaking while the assistant is talking.

### Memory Management

Ganesh remembers facts automatically. You can also manage memories explicitly:

- Add a memory: tell Ganesh to remember something.
- Update a memory: correct or expand existing knowledge.
- Invalidate a memory: mark it as outdated without deleting it.
- Delete a memory: remove it permanently.

### Background Tasks

Ask Ganesh to run a long task. A task ID is returned. You can check its status, cancel it, or wait for the result. All tasks are stored locally in SQLite.

### Plugins

Place plugin folders in `~/.ganesh/plugins/`. Each plugin needs a `manifest.json` and a Python entry point. Ganesh loads them on startup and registers any tools they expose. No SDK is required for simple plugins.

### Profiles

Create multiple user profiles from the settings panel. Each profile has its own memory space. Bridge memory lets profiles share selected knowledge across boundaries.

### Document Viewer

Click a file in chat or drop one into the window. Supported formats: images (PNG, JPG), text files, PDF, and JSON. You can annotate documents and reference them in conversation.

### Themes

Ganesh ships with a single dark theme. You can customize borders, background patterns, and chat bubble colors in the theme settings. Light theme is not available.

### Global Hotkey and System Tray

Minimize Ganesh to the system tray. It stays ready in the background. Press the global hotkey to bring the window to the front from any application.

### Exporting Conversations

Open the history panel, select a conversation, and export it as JSON or Markdown. You can also delete individual conversations or clear all history.

## Configuration

### Config File Location

Ganesh uses a hybrid YAML and JSON configuration system. The main config file lives at:

- **Linux**: `~/.ganesh/config.yaml`
- **Windows**: `%USERPROFILE%\.ganesh\config.yaml`

### API Keys

API keys for cloud providers are stored in the OS keyring, not in plain text on disk.

Supported providers:

| Provider | Key Name | Notes |
|----------|----------|-------|
| OpenAI | `openai` | Default cloud provider |
| Anthropic | `anthropic` | Claude models |
| Google | `google` | Gemini models |
| OpenRouter | `openrouter` | Aggregated access |
| Ollama | none | Local, no key needed |

To set a key via the CLI (for testing):

```bash
python -c "import keyring; keyring.set_password('ganesh', 'openai', 'sk-...')"
```

### LLM Provider Selection

In `config.yaml`, set the active provider:

```yaml
llm:
  provider: openai
  model: gpt-4o
  fallback_provider: ollama
  fallback_model: llama3.1
```

Local providers use LiteLLM's OpenAI-compatible routing. Cloud providers route through LiteLLM as well.

### Voice Settings

```yaml
voice:
  stt_engine: faster-whisper  # or cloud fallback
  tts_engine: piper           # or cloud fallback
  activation_mode: push-to-talk # or wake-word, vad
  barge_in: true
```

### Memory Settings

```yaml
memory:
  backend: lancedb
  embedding_model: all-MiniLM-L6-v2
  max_memories_per_query: 10
```

### Personality Matrix

```yaml
personality:
  base_traits:
    helpfulness: 0.8
    creativity: 0.6
    formality: 0.4
  shift_bounds:
    min: 0.2
    max: 1.0
```

Traits shift dynamically during conversation but stay within the configured bounds.

## Building from Source

### Development Build

```bash
npm run tauri dev
```

### Production Frontend Build

```bash
cd frontend
npm run build
```

### Minimal Installer

The minimal installer bundles the app without AI models. Models download on first run.

**Linux:**

```bash
bash scripts/build-minimal.sh
```

**Windows:**

```powershell
scripts/build-minimal.ps1
```

### Full Installer

The full installer bundles STT, TTS, and embedding models for offline use. Pre-download models into `backend/prebuilt_models/` before building.

**Linux:**

```bash
bash scripts/build-full.sh
```

**Windows:**

```powershell
scripts/build-full.ps1
```

### Output Artifacts

| Platform | Minimal | Full |
|----------|---------|------|
| Linux | `.deb`, `.AppImage` | `.deb`, `.AppImage` |
| Windows | `.msi`, `.exe` | `.msi`, `.exe` |

No macOS builds are produced.

## Testing

### Backend Tests

```bash
cd backend
pytest
```

This runs the full Python test suite including FastAPI endpoint tests, memory tests, and voice pipeline tests.

### Frontend Unit Tests

```bash
cd frontend
npm run test:unit -- --run
```

This runs Vitest with jsdom for React component tests.

### Integration Tests

```bash
cd frontend
npm run test:e2e
```

Playwright drives the Tauri app (or the Vite dev server with a stub sidecar) to test end-to-end flows including sidecar restart, CORS, and UI interactions.

### Rust Tests

```bash
cd src-tauri
cargo test
```

This tests sidecar spawn logic, shutdown hooks, and single-instance locking.

### Running All Checks

```bash
# Python lint and type check
cd backend
ruff check .
mypy .

# TypeScript type check
cd frontend
npx tsc --noEmit

# Rust check
cd src-tauri
cargo check
```

## Troubleshooting

### Sidecar does not start

Check that Python 3.11+ is installed and on your PATH. Run the preflight script to verify. If the sidecar crashes on launch, check the terminal or process output. The sidecar logs to stdout and stderr. There is no separate log file.

### Port binding errors

Ganesh uses ephemeral ports (port 0) for the sidecar. If you see a port conflict, another application may be interfering. Restarting Ganesh usually resolves this.

### CORS errors in the frontend console

The Tauri CSP allows `connect-src` to `http://127.0.0.1:*`. If you modified `tauri.conf.json`, ensure the CSP still permits localhost connections.

### Voice models fail to download (minimal installer)

Check your internet connection and disk space. The download resumes automatically. If it keeps failing, switch to the full installer or manually place models in `~/.ganesh/models/`.

### PyInstaller binary fails to import a module

Run the import check on the frozen binary:

```bash
./dist/ganesh-backend --check-imports
```

If this fails, the dependency may have a native component that needs to be added to `backend/pyinstaller.spec`. See `docs/NATIVE_DEPS.md` for the registry.

### Linux: appindicator or WebView issues

Ensure all system dependencies are installed. Run:

```bash
sudo apt-get install -y libgtk-3-dev libwebkit2gtk-4.0-dev libayatana-appindicator3-dev librsvg2-dev
```

### Windows: WebView2 not found

Install WebView2 from Microsoft's website. Most Windows 10/11 systems already have it.

### Corrupted memory database

Ganesh detects corrupted LanceDB or SQLite files on startup. It will attempt to repair or recreate them. You can also delete `~/.ganesh/data/` (Linux) or `%USERPROFILE%\.ganesh\data\` (Windows) to reset.

### Disk full

If the disk fills up during model download or memory operations, Ganesh pauses and shows a warning. Free up space and retry.

## Contributing

Contributions are welcome. Ganesh is licensed under the PolyForm Noncommercial License 1.0.0, so contributions must be compatible with noncommercial use.

### Getting Started

1. Fork the repository.
2. Run the development setup steps above.
3. Create a branch for your change.
4. Write tests for any new logic.
5. Run the full test suite before submitting.

### Code Style

- **Python**: formatted with ruff, typed with mypy (strict mode), line length 88.
- **TypeScript**: linted with ESLint, checked with `tsc --noEmit`.
- **Rust**: checked with `cargo check` and `cargo clippy`.

### Commit Messages

Use conventional commits:

- `feat:` for new features
- `fix:` for bug fixes
- `docs:` for documentation
- `test:` for tests
- `chore:` for tooling and maintenance

### Reporting Issues

Open an issue on GitHub with:

- Your OS and version
- Ganesh version
- Steps to reproduce
- Expected and actual behavior
- Relevant log excerpts

## License

Ganesh is released under the [PolyForm Noncommercial License 1.0.0](LICENSE).

This license permits personal use, research, education, and noncommercial organization use. Commercial use requires a separate agreement. See the full license text in the `LICENSE` file for details.

---

Built with Tauri v2, React, TypeScript, Tailwind CSS, FastAPI, and Rust.
