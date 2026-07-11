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

- **Chat and voice I/O**. Type messages or speak to Ganesh. Speech-to-text uses faster-whisper locally with a cloud fallback. Text-to-speech uses Kokoro locally with a cloud fallback.
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

Voice settings are configured in-app via the Voice Settings panel (microphone icon in the header). The underlying config keys:

```yaml
voice:
  stt_engine: local        # "local" (faster-whisper) or "cloud" (Deepgram)
  tts_engine: local        # "local" (Kokoro) or "cloud" (ElevenLabs)
  tts_device: auto         # "auto" | "cpu" | "cuda"
  tts_voice_name: af_heart # Kokoro voice name
```

Cloud API keys for Deepgram and ElevenLabs are stored in the OS keyring, not in the config file. Set them via the Voice Settings panel.

### Kokoro TTS Model Setup

Kokoro TTS requires two model files downloaded to `~/.ganesh/models/`:

| File | Size | Description |
|------|------|-------------|
| `kokoro-v1.0.onnx` | ~311 MB | Neural TTS model (ONNX format) |
| `voices-v1.0.bin` | ~27 MB | Voice definitions (all built-in voices) |

Download from the [kokoro-onnx releases page](https://github.com/thewh1teagle/kokoro-onnx/releases/tag/model-files-v1.0):

```bash
mkdir -p ~/.ganesh/models
cd ~/.ganesh/models
wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
```

Install the Python dependencies in the backend venv:

```bash
cd backend
./venv/bin/pip install kokoro-onnx soundfile
```

The system also requires `espeak-ng` for phoneme generation:

```bash
# Linux
sudo apt-get install espeak-ng

# The kokoro-onnx package bundles espeakng-loader as a fallback if the system package is missing.
```

Available voices can be listed via `GET /api/voice/tts-voices` or selected in the Voice Settings panel. The default voice is `af_heart` (American English, female).

### GPU Acceleration (NVIDIA CUDA)

STT (faster-whisper via CTranslate2) and TTS (Kokoro via ONNX Runtime) both support optional NVIDIA GPU acceleration. By default, `stt_device` and `tts_device` are set to `auto`, which detects CUDA and uses it if available. Users without NVIDIA GPUs are unaffected — the app runs on CPU.

#### Prerequisites for GPU acceleration

1. **NVIDIA GPU** with compute capability 6.0+ (Pascal architecture or newer).
2. **NVIDIA driver** installed (any recent version).
3. **CUDA Toolkit** — CTranslate2 bundles its own CUDA runtime, but ONNX Runtime GPU does not. Install the CUDA Toolkit that matches your `onnxruntime-gpu` version:
   ```bash
   # Check which CUDA version onnxruntime-gpu expects:
   cd backend && ./venv/bin/pip show onnxruntime-gpu | grep -i requires

   # Install CUDA Toolkit (example for CUDA 12.x on Ubuntu):
   sudo apt-get install -y cuda-toolkit-12-x
   # For CUDA 13.x, use the NVIDIA developer toolkit repository.
   ```
4. **Install GPU packages** in the backend venv:
   ```bash
   cd backend
   ./venv/bin/pip install onnxruntime-gpu
   # faster-whisper already supports CUDA via CTranslate2 — no extra install needed.
   ```

5. Verify GPU is detected:
   ```bash
   cd backend && ./venv/bin/python -c "
   import ctranslate2; print('CTranslate2 CUDA devices:', ctranslate2.get_cuda_device_count())
   import onnxruntime; print('ONNX providers:', onnxruntime.get_available_providers())
   "
   ```
   You should see `CUDAExecutionProvider` in the ONNX providers list and a non-zero CUDA device count.

If `CUDAExecutionProvider` is missing from the providers list, the CUDA Toolkit or `onnxruntime-gpu` is not installed correctly. The app will fall back to CPU automatically (when `stt_device`/`tts_device` is `auto`).

### Memory Settings

```yaml
memory:
  enabled: true
  max_memories: 1000
```

### LLM Settings

All LLM generation parameters are configurable. Defaults match the provider's standard behavior.

```yaml
llm:
  provider: openai                      # openai | anthropic | google | openrouter | local
  model: gpt-4o-mini                    # default model (used when not overridden per-request)
  local:
    base_url: http://localhost:11434/v1  # Ollama / LM Studio / llama.cpp endpoint
    model: null                          # local model name (null = use llm.model or "local-model")
  models:                               # override the static provider model lists
    openai: [gpt-4o-mini, gpt-4o, gpt-4-turbo, gpt-3.5-turbo]
    anthropic: [claude-3-5-sonnet-20240620, claude-3-5-haiku-20241022, claude-3-opus-20240229]
    google: [gemini-1.5-flash, gemini-1.5-pro, gemini-2.0-flash]
    openrouter: [openai/gpt-4o-mini, anthropic/claude-3.5-sonnet, google/gemini-2.0-flash-001]
    local: []
  temperature: 0.7                      # 0.0-2.0
  max_tokens: 1000
  top_p: 1.0
  frequency_penalty: 0.0                # -2.0 to 2.0
  presence_penalty: 0.0                 # -2.0 to 2.0
  timeout: 10.0                         # seconds for model list fetches
  test_max_tokens: 1                    # tokens used by Test Connection
```

### Voice Settings

Voice settings are configured in-app via the Voice Settings panel (common options) or via config.yaml (all options):

```yaml
voice:
  stt_engine: local              # "local" (faster-whisper) or "cloud" (Deepgram)
  tts_engine: local              # "local" (Kokoro) or "cloud" (ElevenLabs)
  whisper_model: tiny            # tiny|base|small|medium|large|large-v3|large-v3-turbo|distil-large-v3
  stt_device: auto              # "auto" | "cpu" | "cuda"
  tts_device: auto              # "auto" | "cpu" | "cuda"
  activation_mode: click_to_talk # "click_to_talk" | "push_to_talk" | "vad"
  input_device: null            # PulseAudio source name, or null for default
  stt_language: null            # ISO-639-1 code (e.g. "en") or null for auto-detect

  # Deepgram (cloud STT)
  deepgram_model: nova-2
  deepgram_url: https://api.deepgram.com/v1/listen
  deepgram_smart_format: true
  deepgram_punctuate: true
  deepgram_diarize: false
  stt_timeout: 30.0

  # Kokoro (local TTS)
  tts_voice_name: af_heart
  tts_model_path: ""             # empty = ~/.ganesh/models/kokoro-v1.0.onnx
  tts_voices_path: ""            # empty = ~/.ganesh/models/voices-v1.0.bin
  kokoro_speed: 1.0              # 0.5-2.0 (speech rate multiplier)
  kokoro_lang: en-us             # phoneme language

  # ElevenLabs (cloud TTS)
  elevenlabs_voice_id: 21m00Tcm4TlvDq8ikWAM
  elevenlabs_model: eleven_multilingual_v2
  elevenlabs_api_base: https://api.elevenlabs.io/v1
  elevenlabs_stability: null     # 0.0-1.0 (null = don't send)
  elevenlabs_similarity_boost: null  # 0.0-1.0
  elevenlabs_style: null         # 0.0-1.0
  elevenlabs_speed: null         # 0.7-1.2
  tts_timeout: 30.0

  # Audio capture
  max_upload_bytes: 26214400    # 25 MiB upload cap
  audio:
    sample_rate: 16000
    channels: 1
    sample_width: 2

  # Test chime
  chime:
    sample_rate: 22050
    duration: 0.3               # seconds
    frequency: 440.0           # Hz
    fade_ms: 10                # fade in/out duration
```

### Embeddings

```yaml
embeddings:
  model: all-MiniLM-L6-v2      # sentence-transformers model name
  dimension: 384               # embedding vector dimensionality
  lancedb_uri: null            # null = ~/.ganesh/data/lancedb
```

### Personality Matrix

```yaml
personality:
  traits:
    formality: 0.0       # -1.0 (casual) to 1.0 (formal)
    verbosity: 0.0       # -1.0 (concise) to 1.0 (verbose)
    warmth: 0.5          # 0.0 (cold) to 1.0 (warm)
    humor: 0.3           # 0.0 (serious) to 1.0 (playful)
    assertiveness: 0.0   # -1.0 (deferential) to 1.0 (assertive)
  locked: []             # traits that won't shift (e.g. ["humor"])
  mutation_rate_cap: 0.15   # max trait shift per turn
  mutation_scale: 0.05      # scaling factor for context-driven shifts
  trait_bounds:
    formality: [-1.0, 1.0]
    verbosity: [-1.0, 1.0]
    warmth: [0.0, 1.0]
    humor: [0.0, 1.0]
    assertiveness: [-1.0, 1.0]
```

### Conversation Memory (Checkpoint System)

```yaml
conversation_memory:
  enabled: true
  checkpoint_gap_seconds: 300      # gap that triggers a checkpoint (5 min)
  min_messages_for_checkpoint: 2
  max_summaries_injected: 3        # top-k cross-day summaries injected
  full_pull_threshold: 0.85        # similarity for full transcript pull
  max_transcript_messages: 50
  adjacent_segments: 1             # adjacent checkpoints to pull
  summary_provider: null           # null = use same provider as chat
  summary_model: null              # null = use default model for provider
  checkpoint_max_tokens: 200       # target length for checkpoint summaries
  conversation_max_tokens: 500     # target length for conversation summaries
```

### Retrieval

```yaml
retrieval:
  cross_day_threshold: 0.3   # min similarity for cross-day summary injection
  search_limit: 5            # max results from embedding search
```

### Continuity

```yaml
continuity:
  welcome_threshold_seconds: 300   # gap before welcome-back message
```

### Search

```yaml
search:
  backend: duckduckgo
  url: https://html.duckduckgo.com/html/
  default_results: 5
  max_results: 20
  timeout: 10.0
  user_agent: "Mozilla/5.0 ..."
```

### Patterns

```yaml
patterns:
  detection_threshold: 3       # min occurrences before suggesting
  suggestion_confidence: 0.7   # min confidence to suggest
  accept_delta: 0.1            # confidence boost on accept
  decline_delta: -0.2          # confidence penalty on decline
```

### Conversations

```yaml
conversations:
  auto_title_max_len: 50       # max chars for auto-generated titles
  default_title: New Conversation
```

### Model Download

```yaml
model_download:
  chunk_size: 65536            # download chunk size in bytes
  disk_space_safety_multiplier: 2  # warn if free space < N * model size
```

### Summary Embeddings

```yaml
summary_embeddings:
  checkpoint_collection: ganesh_checkpoint_summaries
  conversation_collection: ganesh_conversation_summaries
  pool_limit_multiplier: 10    # pool = max(search_limit * this, pool_limit_min)
  pool_limit_min: 50
```

### Update Settings

```yaml
update:
  channel: stable    # stable | beta
  auto_check: true   # check for updates on launch
```

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
