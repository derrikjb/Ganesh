# Ganesh — Cross-Platform Desktop AI Assistant

## TL;DR

> **Quick Summary**: Build a lightweight, fast desktop AI assistant for Windows + Linux with voice/chat I/O, dynamic self-correcting memory, adaptive personality, sub-agent orchestration, background task management, a plugin system, and a sleek dark UI with modular voice visualizer.
>
> **Deliverables**:
> - Tauri v2 + React/TS desktop app (Windows + Linux)
> - Python FastAPI sidecar (AI logic, voice, memory, orchestration)
> - Chat + voice I/O (faster-whisper STT + Piper TTS, local-first with cloud fallback)
> - Dynamic memory layer (mem0 OSS + LanceDB, explicit add/update/invalidate/delete)
> - Configurable personality trait matrix with dynamic context-based shifting
> - Sub-agent orchestration (custom async task manager + SQLite status store)
> - Python plugin system (dynamic import + manifest)
> - Multiple user profiles with shared bridge memory
> - Modular voice visualizer (waveform, freq bars, holo-face, particles)
> - In-app document viewer (images, text, PDF, JSON) with annotation
> - Theme system (borders, background, chat style/color)
> - System tray + global hotkey + conversation history with export
> - Lifelike features: ambient idle, session continuity, emotional context, proactive suggestions, natural pacing, thinking indicator
> - Both minimal (first-run model download) and full (pre-bundled) installer variants
>
> **Estimated Effort**: XL
> **Parallel Execution**: YES - 6 waves
> **Critical Path**: Wave 0 (sidecar spike) → Wave 1 (MVP chat) → Wave 2 (voice + visualizer) → Wave 3 (tasks + plugins) → Wave 4 (personality + profiles + lifelike) → Wave 5 (polish) → Final Verification

---

## Context

### Original Request
Build a lightweight, fast, cross-platform desktop AI assistant with voice and chat I/O, dynamic memory that can modify/obtain/denounce information, user-nuance learning (fluid, non-rigid), adaptive personality, directory/file navigation, web browsing, document creation, a way to integrate unforeseeable tools, background task management with queryable status, sub-agent orchestration, multi-LLM provider support (cloud + local), minimalist dark UI with modular voice visualizer, document/image viewing, theme support, drag-and-drop files. Written in a fast, easy language with good cross-platform support. Use existing libraries, only write necessary code.

### Interview Summary
**Key Discussions**:
- **Stack**: Python backend (AI/voice/memory/orchestration) + React/TS frontend (UI, visualizer) + Tauri v2 (desktop shell) + FastAPI sidecar (Python-Tauri bridge). Chosen for best AI ecosystem + lightweight desktop.
- **LLM**: OpenAI, Anthropic, Google, OpenRouter (cloud) + all OpenAI-compatible endpoints (local) via LiteLLM routing. Cloud-first MVP, local optional.
- **Orchestration**: Custom async task manager + SQLite status store (start/status/cancel/result), optional LangGraph for complex sub-agent graphs later.
- **Memory**: mem0 OSS + LanceDB (embedded vector store), local embeddings via Ollama. Explicit add/update/invalidate/deny APIs.
- **Personality**: Configurable trait matrix (YAML), dynamic context-based shifting with bounded values to prevent runaway drift.
- **Voice**: faster-whisper (local STT) + Piper (local TTS), cloud fallback (Deepgram, ElevenLabs). Configurable activation (push-to-talk, wake word, VAD).
- **Plugins**: Python dynamic import + manifest (importlib, plugins/ dir).
- **Profiles**: Multiple user profiles with shared bridge memory layer (cross-profile queries with explicit permission model).
- **Platforms**: Windows + Linux (macOS removed — user doesn't want notarization complexity).
- **License**: PolyForm Noncommercial License 1.0.0.
- **Testing**: TDD (pytest + vitest) + agent-executed QA scenarios (Playwright for UI, curl for API).
- **Scope**: Lean MVP first, then layer on features. ALL in ONE plan, phased via waves.

**Research Findings**:
- Python + Tauri recommended over alternatives (best AI ecosystem + lightweight desktop, avoiding Electron bloat).
- Custom lightweight orchestrator recommended over frameworks (best fit for desktop background tasks + queryable status).
- mem0 OSS + LanceDB recommended for local-first memory with explicit mutation APIs.
- faster-whisper + Piper recommended for local-first voice.
- Modular web-based visualizer (Canvas/WebGL/three.js) with plugin interface recommended.

### Metis Review
**Identified Gaps** (addressed):
- **Critical: Wave 0 Foundation Spike** — Must prove Tauri+PyInstaller sidecar works on Win+Linux BEFORE any feature work. Added as Wave 0 with blocking dependency on all subsequent waves.
- **Ephemeral port binding** — Sidecar must bind 127.0.0.1 + ephemeral port, never hardcoded. Added to Wave 0.
- **CORS/CSP validation** — Tauri webview origin (tauri://localhost) to FastAPI (http://127.0.0.1) may be blocked. Added to Wave 0.
- **Single-instance lock** — Two Ganesh instances would collide. Added to Wave 1.
- **Models never bundled in minimal installer** — First-run download with progress UI + checksum + resume. Added to Wave 2.
- **Barge-in state machine** — Concurrent voice + LLM streaming needs interruption policy. Added to Wave 2.
- **Text-only mode** — Accessibility parity for deaf/hard-of-hearing users. Added to Wave 2.
- **Lifelike features need concrete specs** — Each gets falsifiable acceptance criteria. Addressed in Wave 4 task specs.
- **Sidecar crash recovery** — Frontend must detect sidecar death, show reconnecting state, auto-restart. Added to Wave 5.
- **NATIVE_DEPS.md registry** — Track all native Python deps for PyInstaller spec. Added to Wave 0.
- **Playwright integration test layer** — Real app binary + stub LLM for CI. Added to Wave 0.

---

## Work Objectives

### Core Objective
Build a production-quality, lightweight desktop AI assistant that runs on Windows and Linux, with voice + chat I/O, dynamic memory, adaptive personality, extensibility via plugins, and background task management — using existing libraries wherever possible, writing only necessary code.

### Concrete Deliverables
- Working desktop app (Windows .exe + Linux .deb/.AppImage)
- Python FastAPI sidecar (bundled via PyInstaller)
- All features described in TL;DR

### Definition of Done
- [ ] App launches on Windows + Linux with green CI on both
- [ ] User can chat with assistant (text + voice) with streaming responses
- [ ] Assistant stores, retrieves, updates, and deletes memories
- [ ] Assistant runs background tasks with queryable status
- [ ] Plugins can be loaded from ~/.ganesh/plugins/
- [ ] User can switch between profiles with cross-profile bridge memory
- [ ] Voice visualizer renders and is swappable
- [ ] Themes can be applied and switched
- [ ] All tests pass (pytest + vitest + Playwright integration)
- [ ] `curl http://127.0.0.1:$PORT/health` returns `{"status":"ok"}` on both OSes

### Must Have
- Cross-platform: Windows + Linux with green CI on both
- Python + Tauri + React/TS stack
- FastAPI sidecar with ephemeral port + lifecycle management
- LiteLLM for multi-provider routing
- mem0 OSS + LanceDB for memory with explicit mutation
- faster-whisper + Piper for local voice (cloud fallback)
- Custom async task manager + SQLite status store
- Python plugin system (importlib + manifest)
- Modular voice visualizer with plugin interface
- In-app document viewer for common types
- Theme system
- System tray + global hotkey
- Conversation history with export
- Multiple profiles + shared bridge memory
- All lifelike features with concrete falsifiable specs
- TDD throughout (pytest + vitest + Playwright integration)
- Single-instance lock
- OS keyring for API key storage
- YAML + JSON hybrid config

### Must NOT Have (Guardrails)
- NO macOS support (removed — notarization complexity not wanted)
- NO LangGraph in MVP (only added in Wave 3+ if a concrete use case demands it)
- NO plugin SDK in MVP (Wave 3 only — stubs become load-bearing)
- NO multi-LLM-provider adapters in MVP (only OpenAI; LiteLLM handles abstraction)
- NO personality shifting in MVP (Wave 4)
- NO ML models bundled in minimal installer
- NO hardcoded sidecar ports (ephemeral always)
- NO "wip" or "misc" commits
- NO lifelike features without concrete falsifiable specs
- NO acceptance criteria requiring human manual testing
- NO vague QA scenarios ("verify it works" is invalid)
- NO phone-home telemetry without explicit opt-in consent
- NO mobile app, cloud sync, or web app version

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.
> Acceptance criteria requiring "user manually tests/confirms" are FORBIDDEN.

### Test Decision
- **Infrastructure exists**: NO (empty repo)
- **Automated tests**: YES (TDD)
- **Framework**: pytest (Python backend) + vitest (React frontend) + Playwright (integration)
- **TDD**: Each task follows RED (failing test) → GREEN (minimal impl) → REFACTOR

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Frontend/UI**: Use Playwright — Navigate, interact, assert DOM, screenshot
- **Python API**: Use Bash (curl) — Send requests, assert status + response fields
- **Integration**: Use Playwright driving real Tauri app binary + stub LLM
- **Voice**: Use Bash with fixture audio files + curl to STT/TTS endpoints
- **Memory**: Use curl sequence + jq assertions
- **Plugins**: Drop manifest into plugins dir + curl to verify load + invoke
- **CI**: GitHub Actions matrix (windows-latest, ubuntu-latest) — both must pass

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 0 (Foundation Spike — GATE for all features):
├── Task 0: Environment preflight + toolchain verification [quick]
├── Task 1: Repo scaffold + directory structure + git init + license [quick]
├── Task 2: GitHub Actions CI matrix (Win + Linux) [quick] (after Task 1)
├── Task 3: Python FastAPI sidecar + /health endpoint + PyInstaller spec [deep] (after Task 1, parallel with 2)
├── Task 4: Tauri v2 shell + React/TS frontend scaffold + sidecar lifecycle [deep] (after Task 3)
├── Task 5: Playwright integration test layer (real app + stub LLM) [deep] (after Task 4)
└── Task 6: NATIVE_DEPS.md registry + frozen binary native dep CI check [quick] (after Task 3, parallel with 4)

Wave 1 (MVP — Core Chat + Basic Memory + File Browsing + Web Search):
├── Task 7: Design system tokens + dark theme foundation [visual-engineering]
├── Task 8: FastAPI chat endpoint + LiteLLM (OpenAI) + streaming [deep]
├── Task 9: React chat UI (message list, input, streaming display, drag-drop) [visual-engineering]
├── Task 10: mem0 OSS + LanceDB memory layer (store/retrieve/update/delete) [deep]
├── Task 11: File system browsing tool (list, read, navigate dirs) [unspecified-high]
├── Task 12: Web search tool (search API + result parsing) [unspecified-high]
├── Task 13: Config system (YAML settings + JSON) + OS keyring for API keys [quick]
└── Task 14: Single-instance lock + system tray + global hotkey [unspecified-high]

Wave 2 (Voice + Visualizer + Document Viewer + Themes):
├── Task 15: STT integration (faster-whisper local + cloud fallback) [deep]
├── Task 16: TTS integration (Piper local + cloud fallback) [deep]
├── Task 17: Voice activation modes (push-to-talk, wake word, VAD) + barge-in [deep]
├── Task 18: Modular visualizer plugin interface + waveform implementation [visual-engineering]
├── Task 19: Additional visualizer implementations (freq bars, particles, holo-face) [visual-engineering]
├── Task 20: In-app document viewer (images, text, PDF, JSON) + annotation [visual-engineering]
├── Task 21: Theme system (borders, bg, chat style/color) + theme switcher [visual-engineering]
├── Task 22: First-run model download UX (progress, checksum, resume) [unspecified-high]
└── Task 23: Text-only mode (accessibility parity) [unspecified-high]

Wave 3 (Background Tasks + Sub-agents + Plugins + History + Multi-provider):
├── Task 24: Async task manager + SQLite status store (start/status/cancel/result) [deep]
├── Task 25: Sub-agent orchestration (main spawns sub-agents, parses results) [deep]
├── Task 26: Plugin system (importlib + manifest, plugins/ dir, tool registration) [deep]
├── Task 27: Conversation history (search, export JSON/Markdown, delete) [unspecified-high]
├── Task 28: Additional LLM providers (Anthropic, Google, OpenRouter) via LiteLLM [unspecified-high]
└── Task 29: Local LLM support (OpenAI-compat endpoints, Ollama) [unspecified-high]

Wave 4 (Personality + Profiles + Lifelike Features):
├── Task 30: Personality trait matrix (YAML config) + dynamic shifting engine [deep]
├── Task 31: Multiple user profiles + shared bridge memory layer [deep]
├── Task 32: Ambient idle animation (visualizer idle state) [visual-engineering]
├── Task 33: Session continuity memory ("welcome back" + temporal awareness) [unspecified-high]
├── Task 34: Emotional context awareness (tone detection + personality adjustment) [deep]
├── Task 35: Proactive pattern suggestions (fluid, non-rigid learning) [deep]
├── Task 36: Natural response pacing (typing indicator, thinking pauses) [visual-engineering]
└── Task 37: Thinking indicator (visualizer processing state) [visual-engineering]

Wave 5 (Polish + Installer + Error Recovery):
├── Task 38: Installer variants (minimal + full with pre-bundled models) [deep]
├── Task 39: Auto-update (Tauri updater plugin) [unspecified-high]
├── Task 40: Error recovery (sidecar crash, reconnect, corrupted memory, disk full) [deep]
└── Task 41: Bundle size budget enforcement + final CI hardening [quick]

Wave FINAL (After ALL tasks — 4 parallel reviews, then user okay):
├── Task F1: Plan compliance audit (oracle)
├── Task F2: Code quality review (unspecified-high)
├── Task F3: Real manual QA (unspecified-high)
└── Task F4: Scope fidelity check (deep)
-> Present results -> Get explicit user okay

Critical Path: Wave 0 (T0→T1→T3→T4→T5, T2/T6 parallel) → Wave 1 → Wave 2 → Wave 3 → Wave 4 → Wave 5 → F1-F4 → user okay
Parallel Speedup: ~70% faster than sequential
Max Concurrent: 6 (Waves 0 & 1)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 0 | — | 1 | 0 |
| 1 | 0 | 2, 3, 4, 6 | 0 |
| 2 | 1 | all CI-dependent | 0 |
| 3 | 1 | 4, 5, 6 | 0 |
| 4 | 1, 3 | 5, 7, 9, 14 | 0 |
| 5 | 4 | all UI integration tests | 0 |
| 6 | 1, 3 | all Python dep additions | 0 |
| 7 | 4 | 9, 18, 19, 21 | 1 |
| 8 | 3 | 9, 28 | 1 |
| 9 | 7, 8 | 20 | 1 |
| 10 | 3 | 31 | 1 |
| 11 | 3 | — | 1 |
| 12 | 3 | — | 1 |
| 13 | 3 | 8, 28 | 1 |
| 14 | 4 | — | 1 |
| 15 | 4 | 17 | 2 |
| 16 | 4 | 17 | 2 |
| 17 | 15, 16 | — | 2 |
| 18 | 7 | 19, 32, 37 | 2 |
| 19 | 18 | — | 2 |
| 20 | 9 | — | 2 |
| 21 | 7 | — | 2 |
| 22 | 15, 16 | 38 | 2 |
| 23 | 9 | — | 2 |
| 24 | 3 | 25 | 3 |
| 25 | 24 | 26 | 3 |
| 26 | 25 | — | 3 |
| 27 | 10 | — | 3 |
| 28 | 8, 13 | 29 | 3 |
| 29 | 28 | — | 3 |
| 30 | 8, 10 | 34 | 4 |
| 31 | 10 | — | 4 |
| 32 | 18 | — | 4 |
| 33 | 10 | — | 4 |
| 34 | 30 | — | 4 |
| 35 | 10, 30 | — | 4 |
| 36 | 9 | — | 4 |
| 37 | 18 | — | 4 |
| 38 | 22 | 39 | 5 |
| 39 | 38 | — | 5 |
| 40 | 3, 4, 10 | — | 5 |
| 41 | 2 | — | 5 |

### Agent Dispatch Summary

- **Wave 0**: **7 tasks** — T0, T1, T2, T6 → `quick`; T3, T4, T5 → `deep`
- **Wave 1**: **8 tasks** — T7 → `visual-engineering`; T8, T10 → `deep`; T9 → `visual-engineering`; T11, T12, T14 → `unspecified-high`; T13 → `quick`
- **Wave 2**: **9 tasks** — T15, T16, T17 → `deep`; T18, T19, T20, T21 → `visual-engineering`; T22, T23 → `unspecified-high`
- **Wave 3**: **6 tasks** — T24, T25, T26 → `deep`; T27, T28, T29 → `unspecified-high`
- **Wave 4**: **8 tasks** — T30, T31, T34, T35 → `deep`; T32, T36, T37 → `visual-engineering`; T33 → `unspecified-high`
- **Wave 5**: **4 tasks** — T38, T40 → `deep`; T39 → `unspecified-high`; T41 → `quick`
- **FINAL**: **4 tasks** — F1 → `oracle`; F2, F3 → `unspecified-high`; F4 → `deep`

---

## TODOs

- [x] 0. Environment Preflight + Toolchain Verification

  **What to do**:
  - Create a preflight check script (`scripts/preflight.sh` for Linux, `scripts/preflight.ps1` for Windows) that verifies the build environment before any other task runs:
    - **Python**: `python --version` ≥ 3.11 (fail if older)
    - **Node.js**: `node --version` ≥ 20 (fail if older)
    - **npm**: `npm --version` ≥ 10
    - **Rust**: `rustc --version` and `cargo --version` (warn if not installed — Tauri build requires Rust; if missing, print install instructions: `https://rustup.rs/`)
    - **Tauri CLI**: `npx tauri --version` or `cargo tauri --version` (warn if not installed — install via `npm install -D @tauri-apps/cli@2.11.4` or `cargo install tauri-cli`)
    - **System deps (Linux only)**: check for `libwebkit2gtk-4.1-dev`, `libssl-dev`, `libayatana-appindicator3-dev`, `librsvg2-dev` (print install command if missing)
    - **Disk space**: check ≥ 5GB free in working directory (warn if less)
  - Output a summary table of what's installed / missing / version numbers
  - Exit 0 if all hard requirements met, exit 1 if any hard requirement missing
  - Rust is a HARD requirement for this project (Tauri needs it) — if missing, the script prints the install URL and exits 1
  - Write test: `test_preflight_detects_missing_rust` (mock: remove cargo from PATH, assert script exits 1 with message)
  - Commit: `chore: environment preflight check script`

  **Must NOT do**:
  - No installing dependencies automatically (just detect + report)
  - No feature code
  - No project scaffold (Task 1)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (first task, blocks everything)
  - **Parallel Group**: Wave 0
  - **Blocks**: 1
  - **Blocked By**: None

  **References**:
  - **External**: Rust install: `https://rustup.rs/`
  - **External**: Tauri v2 prerequisites: `https://v2.tauri.app/start/prerequisites/` — lists system deps per OS
  - **External**: Tauri CLI: `https://v2.tauri.app/start/create-project/`

  **WHY Each Reference Matters**:
  - Tauri prerequisites: Lists the exact system packages needed on Linux (webkit2gtk, etc.) — without these `cargo build` fails with cryptic errors.

  **Acceptance Criteria**:
  - [ ] `scripts/preflight.sh` exists and runs on Linux
  - [ ] `scripts/preflight.ps1` exists and runs on Windows
  - [ ] Script detects Python, Node, npm, Rust, Tauri CLI presence + versions
  - [ ] Script exits 1 if Rust or Python or Node missing
  - [ ] Script warns (but exits 0) if Tauri CLI missing (will be installed in Task 1)
  - [ ] Script checks Linux system deps and prints install command if missing
  - [ ] `test_preflight_detects_missing_rust` test passes

  **QA Scenarios**:
  ```
  Scenario: Preflight detects all tools present
    Tool: Bash
    Preconditions: Python 3.11+, Node 20+, npm 10+, Rust installed
    Steps:
      1. Run `bash scripts/preflight.sh` (Linux) or `pwsh scripts/preflight.ps1` (Windows)
      2. Assert exit 0
      3. Assert output contains version numbers for all tools
    Expected Result: Exit 0, all tools detected
    Evidence: .sisyphus/evidence/task-0-preflight-pass.txt

  Scenario: Preflight detects missing Rust
    Tool: Bash
    Preconditions: Rust not in PATH (mock by removing from PATH)
    Steps:
      1. Run `PATH=$(echo $PATH | tr ':' '\n' | grep -v cargo | paste -sd:) bash scripts/preflight.sh`
      2. Assert exit 1
      3. Assert output contains "Rust not found" and "https://rustup.rs/"
    Expected Result: Exit 1, clear error message with install URL
    Evidence: .sisyphus/evidence/task-0-preflight-no-rust.txt

  Scenario: Preflight detects missing Linux system deps
    Tool: Bash
    Preconditions: Linux, webkit2gtk not installed
    Steps:
      1. Run `bash scripts/preflight.sh`
      2. Assert output contains "libwebkit2gtk-4.1-dev" and install command
    Expected Result: Missing system deps reported with install instructions
    Evidence: .sisyphus/evidence/task-0-preflight-linux-deps.txt
  ```

  **Commit**: YES
  - Message: `chore: environment preflight check script`

---

- [x] 1. Repo Scaffold + Directory Structure + Git Init + License

  **What to do**:
  - Run preflight (Task 0) first — abort if it fails
  - The repo at `/home/derrik/Projects/ai-projects/Ganesh` is already a git repo (initialized by user). Use the existing repo — do NOT re-clone. If working in a fresh environment, clone from `https://github.com/derrikjb/Ganesh.git`.
  - Create monorepo directory structure:
    - `backend/` (Python FastAPI sidecar: `main.py` stub, `pyproject.toml`, `tests/`)
    - `frontend/` (React/TS — scaffolded in Task 4, but create dir now)
    - `src-tauri/` (Tauri v2 — initialized in Task 4, but create dir now)
    - `.github/workflows/` (CI — Task 2)
    - `docs/` (NATIVE_DEPS.md placeholder)
    - `scripts/` (preflight from Task 0)
    - `.gitignore` (Python, Node, Rust, Tauri ignores — see reference)
  - Add PolyForm Noncommercial License 1.0.0 as `LICENSE`:
    - Fetch full text from: `https://polyformproject.org/licenses/noncommercial/1.0.0`
    - Also available at: `https://github.com/polyformproject/polyform-licenses/blob/1.0.0/PolyForm-Noncommercial-1.0.0.md`
    - Do NOT use a placeholder — fetch the actual full text
  - Add `README.md` with project description, stack overview, and prerequisites (link to preflight script)
  - Set up Python project: `backend/pyproject.toml` with:
    - Build system: `setuptools` or `hatchling`
    - Dependencies: `fastapi`, `uvicorn[standard]`, `litellm`, `pydantic>=2`, `keyring`, `pyyaml`, `python-multipart`
    - Dev dependencies: `pytest`, `pytest-asyncio`, `mypy`, `ruff`, `httpx` (for testing FastAPI)
    - Package name: `ganesh-backend`
  - Set up frontend scaffold using EXACT command:
    - `npm create vite@latest frontend -- --template react-ts`
    - Then: `cd frontend && npm install`
    - Then install Tailwind CSS v4+ (Vite plugin):
      - `cd frontend && npm install tailwindcss @tailwindcss/vite`
      - Add `tailwindcss()` plugin to `vite.config.ts`
      - Add `@import "tailwindcss";` to `src/index.css`
    - Then install vitest + testing-library:
      - `cd frontend && npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom`
      - Create `vitest.config.ts` with `environment: 'jsdom'`, `globals: true`
  - Set up Tauri v2 (only if Rust is available — preflight verified this):
    - `cd frontend && npm install -D @tauri-apps/cli@2.11.4`
    - `cd frontend && npx tauri init` (or `npm create tauri-app@latest` if starting fresh)
    - Configure `src-tauri/tauri.conf.json`: window title "Ganesh", 800x600, dark theme
    - In `src-tauri/Cargo.toml`: pin `tauri = "2.11.5"`
  - Write tests: `test_project_structure` (verify dirs exist, pyproject.toml parses, package.json valid)
  - Initialize git, make first commit: `chore: scaffold repo + project structure`

  **Must NOT do**:
  - No feature code (no chat, no LLM, no memory)
  - No sidecar logic yet (just empty `main.py` with `if __name__ == "__main__": pass`)
  - No CI yet (Task 2)
  - Do NOT use placeholder license text — fetch the real PolyForm Noncommercial 1.0.0 text
  - Do NOT skip the `--template react-ts` flag (vanilla template produces broken React)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (foundation task)
  - **Parallel Group**: Wave 0
  - **Blocks**: 2, 3, 4, 6
  - **Blocked By**: 0

  **References**:
  - **External**: Vite scaffold: `https://vitejs.dev/guide/` — command `npm create vite@latest frontend -- --template react-ts`
  - **External**: Tauri v2 stable: `tauri` crate `2.11.5`, `@tauri-apps/cli` npm `2.11.4` — verified July 2026
  - **External**: Tauri v2 docs: `https://v2.tauri.app/start/create-project/` — project init
  - **External**: Tailwind CSS v4+ Vite setup: `https://tailwindcss.com/docs/installation/using-vite` — uses `@tailwindcss/vite` plugin, NOT old `tailwind.config.js` + PostCSS pattern
  - **External**: vitest setup: `https://vitest.dev/guide/` — requires explicit `npm install -D vitest @testing-library/react @testing-library/jest-dom jsdom` + `vitest.config.ts`
  - **External**: PolyForm Noncommercial 1.0.0: `https://polyformproject.org/licenses/noncommercial/1.0.0` — fetch full text (NO trailing slash)
  - **External**: PyInstaller docs: `https://pyinstaller.org/` — will need .spec in Task 3
  - **Pattern**: `.gitignore` for Tauri+Python+Node: see `https://github.com/github/gitignore` templates

  **WHY Each Reference Matters**:
  - Vite template: Without `--template react-ts`, Vite scaffolds a vanilla JS project. ALL downstream React code will fail. This was a real build failure.
  - Tauri version pin: Tauri v2 went through RCs. Without pinning to `2.11.5` (stable), the executor may pull an RC with breaking API differences.
  - Tailwind v4: The old `npx tailwindcss init -p` command is deprecated. Tailwind v4 uses the `@tailwindcss/vite` plugin pattern — different setup.
  - PolyForm URL: The trailing slash variant (`/1.0.0/`) returns 404. Must use no trailing slash.
  - vitest: Vite does NOT auto-configure vitest. It needs explicit install + config file.

  **Acceptance Criteria**:
  - [ ] `test_project_structure` test passes: all directories exist, configs parse
  - [ ] `cd backend && python -m pytest` runs with 0 failures
  - [ ] `cd frontend && npx vitest run` runs with 0 failures (vitest configured)
  - [ ] `cd frontend && npx tsc --noEmit` succeeds (React+TS template installed correctly)
  - [ ] `cd src-tauri && cargo check` succeeds (IF Rust is available — skip if not, note in evidence)
  - [ ] `LICENSE` file contains full PolyForm Noncommercial 1.0.0 text (first line: "# PolyForm Noncommercial License 1.0.0")
  - [ ] `frontend/package.json` contains `react`, `react-dom`, `@tailwindcss/vite`, `vitest`, `@testing-library/react`
  - [ ] `src-tauri/Cargo.toml` contains `tauri = "2.11.5"`
  - [ ] Git repo has initial commit

  **QA Scenarios**:
  ```
  Scenario: Project structure is valid
    Tool: Bash
    Preconditions: Repo cloned, preflight passed, dependencies installed
    Steps:
      1. Run `test -d backend && test -d frontend && test -d src-tauri && test -d .github/workflows && test -d docs && test -d scripts`
      2. Run `cd backend && python -c "import tomllib; tomllib.load(open('pyproject.toml','rb'))"`
      3. Run `cd frontend && npx tsc --noEmit`
      4. Run `cd src-tauri && cargo check` (skip if Rust not available, note in evidence)
    Expected Result: All commands exit 0
    Evidence: .sisyphus/evidence/task-1-project-structure.txt

  Scenario: Frontend is React+TS (not vanilla)
    Tool: Bash
    Steps:
      1. Run `cat frontend/package.json | grep react`
      2. Assert output contains "react" and "react-dom" and "@types/react"
      3. Run `test -f frontend/src/App.tsx`
      4. Assert file exists (vanilla template would have App.js, not App.tsx)
    Expected Result: React + TypeScript properly scaffolded
    Evidence: .sisyphus/evidence/task-1-frontend-react-ts.txt

  Scenario: License file is real PolyForm text
    Tool: Bash
    Steps:
      1. Run `head -3 LICENSE`
      2. Assert output contains "PolyForm Noncommercial License"
      3. Run `wc -l LICENSE`
      4. Assert line count > 50 (not a placeholder)
    Expected Result: Full license text, not a placeholder
    Evidence: .sisyphus/evidence/task-1-license.txt

  Scenario: Tauri version pinned
    Tool: Bash
    Steps:
      1. Run `grep 'tauri = ' src-tauri/Cargo.toml`
      2. Assert output contains "2.11.5"
    Expected Result: Stable version pinned, not RC
    Evidence: .sisyphus/evidence/task-1-tauri-version.txt

  Scenario: Tailwind v4 Vite plugin installed (not old PostCSS pattern)
    Tool: Bash
    Steps:
      1. Run `cat frontend/package.json | grep tailwind`
      2. Assert output contains "@tailwindcss/vite"
      3. Run `grep tailwindcss frontend/vite.config.ts`
      4. Assert output contains "tailwindcss()" (plugin import)
      5. Run `grep 'import.*tailwindcss' frontend/src/index.css`
      6. Assert output contains '@import "tailwindcss"'
    Expected Result: Tailwind v4 Vite plugin pattern, not old PostCSS
    Evidence: .sisyphus/evidence/task-1-tailwind-v4.txt
  ```

  **Commit**: YES
  - Message: `chore: scaffold repo + project structure`
  - Files: all scaffolded files

---

- [x] 2. GitHub Actions CI Matrix (Windows + Linux)

  **What to do**:
  - Create `.github/workflows/ci.yml` with matrix strategy:
    - `os: [windows-latest, ubuntu-latest]`
    - Steps: checkout, setup Python 3.11+, setup Node 20+, setup Rust (dtolnay/rust-toolchain action), install deps, run preflight, run pytest, run vitest, run `cargo check` (if src-tauri exists)
  - Create `.github/workflows/build.yml` (triggered on tag push):
    - Same matrix, builds PyInstaller sidecar + Tauri app, uploads artifacts
  - Add caching for pip, npm, cargo
  - Write test: verify workflow YAML is valid (parse with `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` — requires `pyyaml` installed)
  - Commit: `chore(ci): add GitHub Actions matrix (win + linux)`

  **Must NOT do**:
  - No macOS in matrix (removed from scope)
  - No notarization steps
  - No actual build steps yet (just test/lint/check)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 3, 6 after Task 1)
  - **Parallel Group**: Wave 0
  - **Blocks**: All CI-dependent tasks
  - **Blocked By**: 1

  **References**:
  - **External**: GitHub Actions matrix strategy: `https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs`
  - **External**: Tauri CI: `https://v2.tauri.app/distribute/ci-cd/`

  **Acceptance Criteria**:
  - [ ] CI workflow YAML is valid (parses without error)
  - [ ] CI runs on push to main and on PRs
  - [ ] Matrix includes `windows-latest` and `ubuntu-latest`
  - [ ] Caching configured for pip, npm, cargo

  **QA Scenarios**:
  ```
  Scenario: CI YAML is valid
    Tool: Bash
    Steps:
      1. Run `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
    Expected Result: Exit 0, no YAML errors
    Evidence: .sisyphus/evidence/task-2-ci-yaml.txt

  Scenario: Matrix includes both OSes
    Tool: Bash
    Steps:
      1. Run `grep -c "windows-latest" .github/workflows/ci.yml`
      2. Run `grep -c "ubuntu-latest" .github/workflows/ci.yml`
    Expected Result: Both return ≥ 1
    Evidence: .sisyphus/evidence/task-2-matrix.txt
  ```

  **Commit**: YES
  - Message: `chore(ci): add GitHub Actions matrix (win + linux)`

---

- [x] 3. Python FastAPI Sidecar + /health Endpoint + PyInstaller Spec

  **What to do**:
  - Create `backend/main.py` with FastAPI app:
    - `GET /health` → `{"status": "ok"}` endpoint
    - CORS middleware configured for Tauri webview origins (`tauri://localhost`, `https://tauri.localhost`)
    - Bind to `127.0.0.1` on ephemeral port (port 0 → OS assigns, write to stdout for Tauri to read)
    - `/shutdown` endpoint for graceful termination
    - SIGTERM/SIGINT handler for clean exit
  - Create `backend/pyinstaller.spec`:
    - Custom spec using `collect_all()` and `collect_dynamic_libs()` from PyInstaller utils
    - Entry point: `main.py`
    - `--onefile` mode
    - Include data files (config templates)
    - Initial deps to collect (NONE are installed yet — these are TEMPLATE entries for when deps are added in later waves):
      ```python
      from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs, collect_submodules

      # Template entries — uncomment/add as deps are introduced in later waves:
      # faster-whisper (Wave 2, Task 15): collect_all('faster_whisper') + collect_all('ctranslate2')
      # piper-tts (Wave 2, Task 16): collect_all('piper') + collect_dynamic_libs('onnxruntime')
      # lancedb (Wave 1, Task 10): collect_submodules('lancedb') + collect_dynamic_libs('pyarrow')
      # mem0ai (Wave 1, Task 10): collect_all('mem0ai')
      # pydantic v2 (Wave 0): collect_submodules('pydantic') + hiddenimports=['pydantic_core']
      # keyring (Wave 1, Task 13): collect_all('keyring')
      ```
    - Each time a native dep is added in a later task, the executor MUST update this .spec AND `NATIVE_DEPS.md`
  - Create `docs/NATIVE_DEPS.md` — registry of native Python deps to track for PyInstaller
  - Write tests (TDD):
    - `test_health_endpoint` — GET /health returns 200 + {"status":"ok"}
    - `test_cors_configured` — CORS headers present for tauri://localhost
    - `test_ephemeral_port` — app binds to port 0 and reports actual port
    - `test_shutdown_endpoint` — POST /shutdown triggers graceful exit
  - Commit: `feat(sidecar): pyinstaller spec + health endpoint`

  **Must NOT do**:
  - No LLM, chat, memory, or voice logic
  - No Tauri integration yet (Task 4 handles spawn)
  - No hardcoded ports

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 2 after Task 1)
  - **Parallel Group**: Wave 0
  - **Blocks**: 4, 5, 6, and all backend-dependent tasks
  - **Blocked By**: 1

  **References**:
  - **Pattern**: `dieharders/example-tauri-v2-python-server-sidecar` (GitHub) — sidecar lifecycle pattern (Rust spawn + stdin/HTTP shutdown)
  - **External**: FastAPI docs: `https://fastapi.tiangolo.com/` — app setup, CORS, lifespan
  - **External**: PyInstaller spec docs: `https://pyinstaller.org/en/stable/spec-files.html`
  - **External**: Tauri sidecar docs: `https://v2.tauri.app/develop/sidecar/`

  **WHY Each Reference Matters**:
  - Sidecar lifecycle pattern: Shows proven Rust-managed spawn + stdin shutdown + HTTP API hybrid. Critical for avoiding orphaned processes.
  - FastAPI CORS: Tauri webview origin is `tauri://localhost` (or `https://tauri.localhost` on Windows) — default CORS will block this. Must configure explicitly.
  - PyInstaller spec: Native extensions (faster-whisper, Piper, LanceDB) need `collect_dynamic_libs` + `hiddenimports` or the frozen binary will ImportError at runtime.

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_health.py` → PASS (4 tests, 0 failures)
  - [ ] `GET /health` returns `{"status":"ok"}` with status 200
  - [ ] CORS headers include `tauri://localhost` and `https://tauri.localhost`
  - [ ] App binds to ephemeral port (port 0) and writes actual port to stdout
  - [ ] `/shutdown` endpoint triggers graceful uvicorn shutdown
  - [ ] `pyinstaller backend/pyinstaller.spec` produces a runnable binary that starts and responds to `GET /health`
  - [ ] `NATIVE_DEPS.md` exists with initial registry (template entries for future deps)

  **QA Scenarios**:
  ```
  Scenario: Health endpoint returns ok
    Tool: Bash (curl)
    Preconditions: Sidecar running on ephemeral port
    Steps:
      1. Start sidecar: `python backend/main.py` (or PyInstaller binary)
      2. Read port from stdout
      3. `curl -s http://127.0.0.1:$PORT/health`
      4. Assert JSON response: `{"status":"ok"}`
    Expected Result: 200 status, body contains "ok"
    Failure Indicators: Connection refused, non-200 status, missing "ok" in response
    Evidence: .sisyphus/evidence/task-3-health.txt

  Scenario: CORS configured for Tauri origins
    Tool: Bash (curl)
    Steps:
      1. `curl -s -I -H "Origin: tauri://localhost" http://127.0.0.1:$PORT/health`
      2. Assert `Access-Control-Allow-Origin` header contains `tauri://localhost`
      3. Repeat with `Origin: https://tauri.localhost`
    Expected Result: CORS headers present for both Tauri origins
    Evidence: .sisyphus/evidence/task-3-cors.txt

  Scenario: Sidecar binds ephemeral port
    Tool: Bash
    Steps:
      1. Start sidecar, capture stdout
      2. Assert stdout contains a port number > 1024
      3. `curl http://127.0.0.1:$PORT/health` succeeds
    Expected Result: Port is dynamically assigned, not hardcoded
    Evidence: .sisyphus/evidence/task-3-ephemeral-port.txt

  Scenario: Shutdown endpoint terminates gracefully
    Tool: Bash
    Steps:
      1. Start sidecar, get port
      2. `curl -X POST http://127.0.0.1:$PORT/shutdown`
      3. Wait 3s
      4. `curl http://127.0.0.1:$PORT/health` — expect connection refused
    Expected Result: Sidecar process exits, port no longer listening within 3s
    Evidence: .sisyphus/evidence/task-3-shutdown.txt
  ```

  **Commit**: YES
  - Message: `feat(sidecar): pyinstaller spec + health endpoint`

---

- [x] 4. Tauri v2 Shell + React/TS Frontend Scaffold + Sidecar Lifecycle

  **What to do**:
  - Configure `src-tauri/tauri.conf.json`:
    - Window: title "Ganesh", dark theme, 800x600 default size
    - Product name, identifier (`com.ganesh.desktop`), version 0.1.0
    - Frontend dist path: `../frontend/dist`
    - Security: CSP allowing `connect-src` to `http://127.0.0.1:*` (for sidecar)
  - Configure `src-tauri/Cargo.toml`:
    - `tauri = { version = "2.11.5", features = ["tray-icon"] }` — tray is a FEATURE FLAG on the core crate, NOT a separate plugin
    - `tauri-plugin-global-shortcut = "2"` (for global hotkey, Task 14)
    - `tauri-plugin-single-instance = "2"` (for single-instance lock)
    - Do NOT use `tauri-plugin-tray` or `tauri-plugin-system-tray` — these do NOT exist. Tray functionality is built into the core `tauri` crate via the `tray-icon` feature.
  - Implement `src-tauri/src/main.rs`:
    - Spawn Python sidecar binary as child process (using Tauri sidecar API or `Command::new`)
    - Read port from sidecar stdout
    - Store port in app state, expose to frontend via Tauri command
    - `RunEvent::ExitRequested` hook: send SIGTERM to sidecar, wait with timeout
    - Single-instance lock (Tauri `tauri-plugin-single-instance`)
  - Frontend scaffold (`frontend/src/`):
    - `App.tsx` with minimal layout (header, main area, footer)
    - `api.ts` — Tauri command to get sidecar port + fetch wrapper
    - `useSidecar.ts` hook — health check on mount, reconnect logic
    - Dark theme via Tailwind (already configured in Task 1)
  - Write tests:
    - Rust: `test_sidecar_spawn` (mock sidecar, verify spawn + port read)
    - Rust: `test_shutdown` (verify SIGTERM sent on exit)
    - TS: `test_use_sidecar` (mock Tauri command, verify health check)
  - Commit: `feat(tauri): shell + sidecar lifecycle + frontend scaffold`

  **Must NOT do**:
  - No chat UI (Task 9)
  - No actual LLM integration
  - No system tray (Task 14)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Task 3 sidecar code — the FastAPI app + /health endpoint must exist so Tauri can spawn it. In dev, Tauri spawns `python backend/main.py` directly, NOT the PyInstaller frozen binary.)
  - **Parallel Group**: Wave 0
  - **Blocks**: 5, 7, 9, 14
  - **Blocked By**: 1, 3

  **References**:
  - **Pattern**: `dieharders/example-tauri-v2-python-server-sidecar` — Rust sidecar spawn + lifecycle
  - **External**: Tauri v2 sidecar: `https://v2.tauri.app/develop/sidecar/`
  - **External**: Tauri v2 system tray: `https://v2.tauri.app/learn/system-tray/` — tray is a feature flag (`features = ["tray-icon"]`), NOT a plugin crate
  - **External**: Tauri single-instance plugin: `https://v2.tauri.app/plugin/single-instance/`
  - **External**: Tauri CSP config: `https://v2.tauri.app/security/csp/`
  - **External**: Tauri v2 stable: `tauri` crate `2.11.5`, `@tauri-apps/cli` npm `2.11.4` (verified July 2026)

  **WHY Each Reference Matters**:
  - Sidecar pattern: Shows how Rust spawns, monitors, and shuts down the Python process. Critical for avoiding orphaned uvicorn processes.
  - CSP: Tauri's default CSP blocks `http://` requests from the webview. Must explicitly allow `connect-src: http://127.0.0.1:*` or the frontend can't reach the sidecar.
  - Single-instance: Two Ganesh launches = two sidecars = port collision. Lock from launch.

  **Acceptance Criteria**:
  - [ ] `cargo test` passes (sidecar spawn + shutdown tests)
  - [ ] `cd frontend && npx vitest run` passes (useSidecar hook test)
  - [ ] `cargo tauri dev` launches app with dark window
  - [ ] Sidecar starts automatically on app launch
  - [ ] Frontend receives sidecar port via Tauri command
  - [ ] `GET /health` from frontend succeeds (visible in console)
  - [ ] Quitting app sends SIGTERM to sidecar, port freed within 3s
  - [ ] Second app launch focuses first window (single-instance lock)

  **QA Scenarios**:
  ```
  Scenario: App launches and sidecar is healthy
    Tool: Playwright (Tauri WebDriver) or Bash
    Preconditions: App built, sidecar binary available
    Steps:
      1. Launch app: `cargo tauri dev` or run built binary
      2. Wait for window to appear (timeout 10s)
      3. Check frontend console for health check success
      4. `curl http://127.0.0.1:$PORT/health` from within app context
    Expected Result: App window visible, sidecar health check passes, console shows "sidecar: ok"
    Evidence: .sisyphus/evidence/task-4-app-launch.png (screenshot)

  Scenario: Sidecar terminates on app quit
    Tool: Bash
    Steps:
      1. Launch app, get sidecar port
      2. Quit app (close window or SIGTERM to Tauri process)
      3. Wait 3s
      4. `lsof -i:$PORT` (Linux) or `netstat -ano | findstr $PORT` (Windows)
    Expected Result: No process listening on sidecar port within 3s
    Evidence: .sisyphus/evidence/task-4-sidecar-terminate.txt

  Scenario: Single instance lock prevents double launch
    Tool: Bash
    Steps:
      1. Launch app (first instance)
      2. Launch app again (second instance)
      3. Assert second instance focuses first window and exits
      4. Assert only one sidecar process running
    Expected Result: One app window, one sidecar process
    Evidence: .sisyphus/evidence/task-4-single-instance.txt
  ```

  **Commit**: YES
  - Message: `feat(tauri): shell + sidecar lifecycle + frontend scaffold`

---

- [x] 5. Playwright Integration Test Layer (Real App + Stub LLM)

  **What to do**:
  - Set up Playwright with Tauri WebDriver for integration testing:
    - Install `tauri-driver` binary (cargo install tauri-driver or download prebuilt)
    - Configure Playwright to use Tauri's WebDriver protocol (not standard browser)
    - `playwright.config.ts` with WebDriver capability for Tauri
    - Alternative if Tauri WebDriver is complex: use Playwright against the frontend dev server (Vite) with a stub sidecar running on a known port — this tests frontend logic without the full Tauri binary
  - Test fixture: stub LLM endpoint (mock FastAPI route returning canned responses)
  - Test fixture: clean state (no persisted memory, fresh config)
  - Create integration tests:
    - `test_app_launch` — app launches (or dev server starts), sidecar healthy, UI renders
    - `test_sidecar_restart` — kill sidecar, verify frontend shows reconnecting state
    - `test_cors` — frontend can fetch from sidecar (no CORS errors in console)
  - Create test helpers:
    - `waitForSidecar(port)` — poll /health until ok
    - `startStubLLM()` — start mock LLM server returning canned responses
    - `startStubSidecar(port)` — start a minimal FastAPI stub on a fixed port for testing
  - Commit: `test: add Playwright integration test layer`

  **Must NOT do**:
  - No UI feature tests (those go in respective feature tasks)
  - No real LLM calls (stub only)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on Task 4 app being functional)
  - **Parallel Group**: Wave 0
  - **Blocks**: All UI integration tests in subsequent waves
  - **Blocked By**: 4

  **References**:
  - **External**: Tauri WebDriver: `https://v2.tauri.app/develop/tests/webdriver/` — requires `tauri-driver` binary
  - **External**: tauri-driver install: `cargo install tauri-driver` or prebuilt binary
  - **External**: Playwright config: `https://playwright.dev/docs/test-configuration`
  - **External**: Tauri testing guide: `https://v2.tauri.app/develop/tests/`
  - **Fallback pattern**: If Tauri WebDriver is too complex for CI, test frontend via Vite dev server + stub FastAPI sidecar on a fixed port (e.g., 18008). This tests frontend logic without the full Tauri binary. Full app integration tested in Final Verification (F3).

  **Acceptance Criteria**:
  - [ ] `npx playwright test` runs and passes 3 integration tests
  - [ ] Stub LLM fixture works (canned responses served)
  - [ ] Test helpers (`waitForSidecar`, `startStubLLM`, `startStubSidecar`) are reusable
  - [ ] Playwright config added to CI workflow (update `.github/workflows/ci.yml` from Task 2)

  **QA Scenarios**:
  ```
  Scenario: Integration tests pass
    Tool: Bash
    Steps:
      1. `cd frontend && npx playwright test`
      2. Assert exit 0
    Expected Result: 3 tests pass (app launch, sidecar restart, CORS)
    Evidence: .sisyphus/evidence/task-5-playwright-results.txt

  Scenario: Sidecar restart test
    Tool: Playwright
    Steps:
      1. Launch app (via test fixture)
      2. Verify health check passes
      3. Kill sidecar process
      4. Wait 5s
      5. Assert frontend shows "reconnecting" state
      6. Wait for auto-restart (if implemented) or verify error state
    Expected Result: Frontend detects sidecar death and shows appropriate state
    Evidence: .sisyphus/evidence/task-5-sidecar-restart.png
  ```

  **Commit**: YES
  - Message: `test: add Playwright integration test layer`
  - Pre-commit: `npx playwright test`

---

- [x] 6. NATIVE_DEPS.md Registry + Frozen Binary Native Dep CI Check

  **What to do**:
  - Populate `docs/NATIVE_DEPS.md` with initial registry of native Python deps:
    - `fastapi`, `uvicorn` (pure Python, no special handling)
    - `litellm` (check for native components)
    - `pydantic` (Rust-backed in v2, needs collect_dynamic_libs)
    - `keyring` (platform-specific backends)
    - Future deps to add later: `faster-whisper`, `piper-tts`, `lancedb`, `sounddevice`
  - Add CI step in `.github/workflows/ci.yml`:
    - Build PyInstaller binary (using spec from Task 3)
    - Run frozen binary with a health check: `./dist/ganesh-sidecar &` then `curl http://127.0.0.1:$PORT/health`
    - Alternatively, run: `./dist/ganesh-sidecar --check-imports` where `--check-imports` is a custom CLI flag in `main.py` that imports all registered native deps and exits 0/1
    - Add `--check-imports` flag to `backend/main.py`: when passed, imports `fastapi, uvicorn, litellm, pydantic, keyring` (and future deps as added), prints success/failure, exits 0/1
    - Fail CI if any ImportError or if health check fails
  - Add test: `test_native_deps_import` — runs `python -c "import fastapi, uvicorn, litellm, pydantic, keyring"` and asserts exit 0
  - Commit: `docs: NATIVE_DEPS registry + CI native dep check`

  **Must NOT do**:
  - No voice/memory deps yet (those are added in later waves)
  - No actual feature code

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 2 after Task 1, Task 3)
  - **Parallel Group**: Wave 0
  - **Blocks**: All Python dep additions (CI will catch missing native deps)
  - **Blocked By**: 1, 3

  **References**:
  - **External**: PyInstaller hidden imports: `https://pyinstaller.org/en/stable/spec-files.html#collecting-submodules-and-data`
  - **Pattern**: `benitomartin/tauri-app-bundle` (GitHub) — custom .spec with collect_dynamic_libs

  **Acceptance Criteria**:
  - [ ] `NATIVE_DEPS.md` exists with current dep registry
  - [ ] CI step builds PyInstaller binary and imports all native deps
  - [ ] CI fails if any native dep ImportError

  **QA Scenarios**:
  ```
  Scenario: Frozen binary imports all native deps
    Tool: Bash
    Preconditions: PyInstaller binary built
    Steps:
      1. Build: `pyinstaller backend/pyinstaller.spec`
      2. Run: `./dist/ganesh-sidecar --check-imports`
      3. Assert exit 0
    Expected Result: All native deps importable inside frozen binary
    Evidence: .sisyphus/evidence/task-6-native-deps.txt

  Scenario: Frozen binary starts and responds to health check
    Tool: Bash
    Preconditions: PyInstaller binary built
    Steps:
      1. Run: `./dist/ganesh-sidecar &`
      2. Read port from stdout
      3. `curl -s http://127.0.0.1:$PORT/health`
      4. Assert `{"status":"ok"}`
      5. Kill sidecar
    Expected Result: Frozen binary functional
    Evidence: .sisyphus/evidence/task-6-frozen-health.txt
  ```

  **Commit**: YES
  - Message: `docs: NATIVE_DEPS registry + CI native dep check`

---

- [x] 7. Design System Tokens + Dark Theme Foundation

  **What to do**:
  - Create `frontend/src/styles/tokens.css` with CSS custom properties: colors (`--bg-primary` #0a0a0a, `--bg-secondary` #1a1a1a, `--text-primary` #e0e0e0, `--accent` #3b82f6, `--border` #333), spacing (`--space-xs` 4px through `--space-xl` 32px), typography (font stacks, text sizes), radius, transitions
  - Create `frontend/src/styles/theme.css` — theme variables referencing tokens, overridable by theme plugins
  - Configure Tailwind dark mode with CSS custom properties
  - Create `ThemeContext.tsx` — React context for theme switching (default: dark)
  - Write tests: token parsing, theme context provides correct values
  - Commit: `feat(ui): design system tokens + dark theme foundation`

  **Must NOT do**: No theme switching UI (Task 21), no actual components beyond layout shell

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering` — UI/design system work
  - **Skills**: []

  **Parallelization**: YES (with Tasks 8, 10, 11, 12, 13, 14) | Wave 1 | Blocks: 9, 18, 19, 21 | Blocked By: 4

  **References**:
  - **External**: Tailwind CSS v4 dark mode: `https://tailwindcss.com/docs/dark-mode` — note: Tailwind v4 uses CSS `@media (prefers-color-scheme: dark)` or manual class strategy via `@variant dark`
  - **External**: CSS custom properties: `https://developer.mozilla.org/en-US/docs/Web/CSS/--*`

  **Acceptance Criteria**:
  - [ ] `tokens.css` defines all CSS custom properties
  - [ ] `vitest` passes (token + theme context tests)
  - [ ] App renders with dark theme (bg #0a0a0a visible)

  **QA Scenarios**:
  ```
  Scenario: Dark theme renders correctly
    Tool: Playwright
    Steps:
      1. Launch app
      2. Assert `body` background-color computed value is rgb(10, 10, 10)
      3. Assert primary text color is readable (contrast ratio > 4.5:1)
    Expected Result: Dark background, readable text
    Evidence: .sisyphus/evidence/task-7-dark-theme.png
  ```

  **Commit**: YES | Message: `feat(ui): design system tokens + dark theme foundation`

---

- [x] 8. FastAPI Chat Endpoint + LiteLLM (OpenAI) + Streaming

  **What to do**:
  - Create `backend/chat.py`: `POST /chat` accepting `{message, conversation_id}`, using LiteLLM with OpenAI provider (default `gpt-4o-mini`), streaming via SSE
  - Create `backend/llm_router.py`: LiteLLM wrapper with config-driven provider selection
    - API key retrieval: try OS keyring first (`keyring.get("ganesh", "api_key_openai")`), fall back to `OPENAI_API_KEY` env var for dev/testing
    - Streaming via `litellm.acompletion(stream=True)`
  - Error handling: 401 (invalid key), 429 (rate limit), 500 (LLM error)
  - Conversation context: stub (retrieve last N messages — Task 10 integration later)
  - Write tests (TDD): `test_chat_endpoint`, `test_chat_streaming`, `test_chat_error_401`, `test_chat_error_429`, `test_llm_router_config`
  - Commit: `feat(chat): FastAPI chat endpoint + LiteLLM streaming`

  **Must NOT do**: No Anthropic/Google/OpenRouter (Task 28), no local LLM (Task 29), no memory integration yet, no personality (Task 30)

  **Recommended Agent Profile**:
  - **Category**: `deep` — core AI logic
  - **Skills**: []

  **Parallelization**: YES (with Tasks 7, 10, 11, 12, 13, 14) | Wave 1 | Blocks: 9, 28 | Blocked By: 3 (sidecar), 13 (config — but can stub with env var if 13 not done yet)

  **References**:
  - **External**: LiteLLM docs: `https://docs.litellm.ai/docs/` — completion, streaming, provider config
  - **External**: FastAPI StreamingResponse: `https://fastapi.tiangolo.com/advanced/custom-response/`
  - **External**: LiteLLM streaming: `https://docs.litellm.ai/docs/streaming`

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_chat.py` → PASS (5 tests, 0 failures)
  - [ ] `POST /chat` returns SSE stream with text chunks
  - [ ] 401 on invalid key, 429 on rate limit (mocked)

  **QA Scenarios**:
  ```
  Scenario: Chat endpoint streams response
    Tool: Bash (curl)
    Preconditions: Sidecar running, OPENAI_API_KEY set (or mock)
    Steps:
      1. `curl -N -X POST http://127.0.0.1:$PORT/chat -H "Content-Type: application/json" -d '{"message":"Say hello","conversation_id":"test1"}'`
      2. Assert SSE chunks received (data: prefix lines)
      3. Assert final chunk contains [DONE] or completion signal
    Expected Result: Streaming text response
    Evidence: .sisyphus/evidence/task-8-chat-stream.txt

  Scenario: Invalid API key returns 401
    Tool: Bash (curl)
    Steps:
      1. Set invalid API key
      2. POST /chat with any message
      3. Assert HTTP 401
    Expected Result: 401 status with error message
    Evidence: .sisyphus/evidence/task-8-401.txt
  ```

  **Commit**: YES | Message: `feat(chat): FastAPI chat endpoint + LiteLLM streaming`

---

- [x] 9. React Chat UI (Message List, Input, Streaming Display, Drag-Drop)

  **What to do**:
  - Create `frontend/src/components/chat/`: `ChatWindow.tsx` (message list + auto-scroll), `Message.tsx` (user vs assistant styling, markdown rendering via react-markdown), `ChatInput.tsx` (text input, Enter to send, Shift+Enter newline), `TypingIndicator.tsx`, `DragDropZone.tsx` (drag-drop file area + preview + upload)
  - Create `frontend/src/hooks/useChat.ts`: conversation state, SSE connection, stream chunk appending
  - Create `frontend/src/api/sidecar.ts`: `streamChat()` with SSE parsing, `uploadFile()` multipart
  - Write tests: `test_chat_window`, `test_chat_input`, `test_streaming`, `test_drag_drop`
  - Commit: `feat(ui): chat window + streaming + drag-drop`

  **Must NOT do**: No voice input (Task 15+), no visualizer (Task 18+), no conversation history persistence (Task 27), no document viewer (Task 20)

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering` — React UI components
  - **Skills**: []

  **Parallelization**: YES (with Tasks 10, 11, 12, 13, 14) | Wave 1 | Blocks: 20, 23 | Blocked By: 7, 8

  **References**:
  - **Pattern**: Task 7 tokens — use CSS custom properties for styling
  - **External**: react-markdown: `https://github.com/remarkjs/react-markdown`
  - **External**: SSE in browser: `https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events`
  - **Note**: Tauri webview origin (`tauri://localhost` or `https://tauri.localhost`) fetching `http://127.0.0.1:$PORT` may face mixed-content or CORS issues. Use `fetch()` with streaming response body parsing (ReadableStream) instead of `EventSource` if EventSource fails, OR configure Tauri's `allowedUrls`/CSP to permit the sidecar origin (configured in Task 4).

  **Acceptance Criteria**:
  - [ ] `vitest` passes (4 component tests)
  - [ ] Playwright: type message, Enter, see streaming response
  - [ ] Messages render markdown (bold, code blocks, links)
  - [ ] Drag-and-drop file shows preview + uploads to sidecar
  - [ ] Auto-scroll to bottom on new message

  **QA Scenarios**:
  ```
  Scenario: User sends a chat message and receives streamed response
    Tool: Playwright
    Preconditions: App running, sidecar healthy, stub LLM returning "Hello!"
    Steps:
      1. Click chat input (`[data-testid="chat-input"]`)
      2. Type "Hello Ganesh"
      3. Press Enter
      4. Assert user message appears (`[data-testid="message-user-0"]`)
      5. Wait for response (timeout 10s)
      6. Assert assistant message (`[data-testid="message-assistant-0"]`) contains "Hello!"
    Expected Result: User + assistant messages visible, streaming works
    Evidence: .sisyphus/evidence/task-9-chat-flow.png

  Scenario: Drag and drop a file
    Tool: Playwright
    Steps:
      1. Create temp file `test.txt` with content "test"
      2. Drop onto `[data-testid="chat-window"]`
      3. Assert file preview appears (`[data-testid="file-preview"]`)
      4. Assert upload triggered (sidecar receives file)
    Expected Result: File preview shown, upload triggered
    Evidence: .sisyphus/evidence/task-9-drag-drop.png
  ```

  **Commit**: YES | Message: `feat(ui): chat window + streaming + drag-drop`

---

- [x] 10. mem0 OSS + LanceDB Memory Layer (Store/Retrieve/Update/Delete)

  **What to do**:
  - Create `backend/memory.py`: Initialize mem0 OSS with LanceDB backend (stored in `~/.ganesh/data/lancedb/`), local embeddings via Ollama (`nomic-embed-text`) with sentence-transformers fallback
  - Endpoints: `POST /memories` (store), `GET /memories?query=&user_id=` (search), `PUT /memories/{id}` (update), `DELETE /memories/{id}` (delete), `GET /memories/all?user_id=` (list), `POST /memories/invalidate/{id}` (soft-delete with reason, excluded from search)
  - Create `backend/memory_config.py`: mem0 config with LanceDB vector config, embedding model config, storage path
  - Integrate with chat: retrieve relevant memories before LLM call, optionally store new facts after response
  - Write tests (TDD): `test_store_memory`, `test_search_memory`, `test_update_memory`, `test_delete_memory`, `test_invalidate_memory`, `test_memory_isolation` (user A ≠ user B), `test_memory_persistence` (survives restart)
  - Update NATIVE_DEPS.md: add `mem0ai` (PyPI package name, imported as `mem0`), `lancedb`, `sentence-transformers`
  - Commit: `feat(memory): mem0 + LanceDB with explicit mutation APIs`

  **Must NOT do**: No profiles yet (Task 31), no bridge memory (Task 31), no personality (Task 30), no session continuity (Task 33)

  **Recommended Agent Profile**:
  - **Category**: `deep` — complex memory architecture
  - **Skills**: []

  **Parallelization**: YES (with Tasks 7, 8, 11, 12, 13, 14) | Wave 1 | Blocks: 27, 31, 33, 35 | Blocked By: 3

  **References**:
  - **External**: mem0 docs: `https://docs.mem0.ai/` — add, search, update, delete, invalidate APIs
  - **External**: mem0 OSS GitHub: `https://github.com/mem0ai/mem0` — PyPI package is `mem0ai`, imported as `import mem0`
  - **External**: LanceDB Python: `https://lancedb.github.io/lancedb/` — embedded vector store
  - **External**: Ollama embeddings: `https://ollama.com/blog/embedding-models`

  **WHY Each Reference Matters**:
  - mem0 docs: Explicit add/update/delete/invalidate APIs are the core requirement. Follow their API surface, not custom mutation logic.
  - LanceDB: Embedded, in-process, disk-resident — perfect for desktop, no server process needed.
  - Ollama embeddings: Local embedding generation. Fallback to sentence-transformers if Ollama unavailable.

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_memory.py` → PASS (7 tests, 0 failures)
  - [ ] Store → search → retrieve works semantically
  - [ ] Update changes content, delete removes, invalidate excludes from search
  - [ ] Memories persist across sidecar restart
  - [ ] User A's memories not returned for user B

  **QA Scenarios**:
  ```
  Scenario: Memory round-trip (store → search → retrieve)
    Tool: Bash (curl)
    Steps:
      1. POST /memories {"content":"User likes Python", "user_id":"u1"} → get id
      2. GET /memories?query="what language does user like"&user_id=u1
      3. Assert "Python" in results
    Expected Result: Stored memory is semantically retrievable
    Evidence: .sisyphus/evidence/task-10-memory-roundtrip.txt

  Scenario: Memory invalidation excludes from search
    Tool: Bash (curl)
    Steps:
      1. POST /memories {"content":"User lives in New York", "user_id":"u1"} → id
      2. POST /memories/invalidate/{id} {"reason":"user moved to London"}
      3. GET /memories?query="where does user live"&user_id=u1
      4. Assert "New York" NOT in results
    Expected Result: Invalidated memory excluded from search
    Evidence: .sisyphus/evidence/task-10-invalidation.txt

  Scenario: Memory persists across restart
    Tool: Bash (curl)
    Steps:
      1. POST /memories {"content":"test persistence", "user_id":"u1"}
      2. Restart sidecar
      3. GET /memories?query="persistence"&user_id=u1
      4. Assert "test persistence" in results
    Expected Result: Memory survived restart
    Evidence: .sisyphus/evidence/task-10-persistence.txt

  Scenario: User isolation
    Tool: Bash (curl)
    Steps:
      1. POST /memories {"content":"user A secret", "user_id":"uA"}
      2. GET /memories?query="secret"&user_id=uB
      3. Assert "user A secret" NOT in results
    Expected Result: Cross-user memory leak prevented
    Evidence: .sisyphus/evidence/task-10-isolation.txt
  ```

  **Commit**: YES | Message: `feat(memory): mem0 + LanceDB with explicit mutation APIs`

---

- [x] 11. File System Browsing Tool (List, Read, Navigate Directories)

  **What to do**:
  - Create `backend/tools/filesystem.py`: `POST /tools/filesystem/list` (list dir contents with name/type/size/modified), `POST /tools/filesystem/read` (read file with max_bytes truncation), `GET /tools/filesystem/home` (user home dir)
  - Security: block system paths (`/etc`, `/proc` on Linux; `C:\Windows` on Windows), return 403
  - File type detection (text, image, pdf, json, binary)
  - Register as LLM tools via LiteLLM: `list_directory(path)`, `read_file(path, max_bytes)`
  - Write tests (TDD): `test_list_directory`, `test_read_file`, `test_blocked_paths`, `test_large_file_truncation`
  - Commit: `feat(tools): filesystem browsing (list, read, navigate)`

  **Must NOT do**: No file writing/modification, no document viewer UI (Task 20)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high` | **Skills**: []
  - **Parallelization**: YES (with 7, 8, 10, 12, 13, 14) | Wave 1 | Blocks: None | Blocked By: 3

  **References**:
  - **External**: LiteLLM function calling: `https://docs.litellm.ai/docs/function_calling`

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_filesystem.py` → PASS (4 tests)
  - [ ] List returns directory contents, read returns file content
  - [ ] System paths return 403, large files truncated with flag

  **QA Scenarios**:
  ```
  Scenario: List home directory
    Tool: Bash (curl)
    Steps:
      1. GET /tools/filesystem/home → get home path
      2. POST /tools/filesystem/list {"path": "<home>"} → get contents
      3. Assert array with name/type/size fields
    Expected Result: Non-empty array of files/dirs
    Evidence: .sisyphus/evidence/task-11-list-dir.txt

  Scenario: System paths blocked
    Tool: Bash (curl)
    Steps:
      1. POST /tools/filesystem/read {"path": "/etc/passwd"} (Linux)
      2. Assert HTTP 403
    Expected Result: Security restriction enforced
    Evidence: .sisyphus/evidence/task-11-blocked-paths.txt
  ```

  **Commit**: YES | Message: `feat(tools): filesystem browsing (list, read, navigate)`

---

- [x] 12. Web Search Tool (Search API + Result Parsing)

  **What to do**:
  - Create `backend/tools/websearch.py`: `POST /tools/websearch` (search via duckduckgo-search, no API key needed, returns title/url/snippet), `POST /tools/websearch/fetch` (fetch URL, extract content via trafilatura)
  - Rate limiting: max 1 req/sec
  - Register as LLM tools: `web_search(query, max_results)`, `fetch_url(url)`
  - Write tests (TDD): `test_websearch`, `test_fetch_url`, `test_rate_limiting`
  - Commit: `feat(tools): web search + URL fetch`

  **Must NOT do**: No browser automation (just search + fetch), no screenshots

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high` | **Skills**: []
  - **Parallelization**: YES (with 7, 8, 10, 11, 13, 14) | Wave 1 | Blocks: None | Blocked By: 3

  **References**:
  - **External**: duckduckgo-search: `https://github.com/deedy5/duckduckgo_search`
  - **External**: trafilatura: `https://trafilatura.readthedocs.io/`

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_websearch.py` → PASS (3 tests)
  - [ ] Search returns results with title/url/snippet
  - [ ] Fetch returns extracted content, rate limiting enforced

  **QA Scenarios**:
  ```
  Scenario: Web search returns results
    Tool: Bash (curl)
    Steps:
      1. POST /tools/websearch {"query": "Python programming", "max_results": 3}
      2. Assert array with title/url/snippet, ≥ 1 result
    Expected Result: Non-empty search results
    Evidence: .sisyphus/evidence/task-12-websearch.txt
  ```

  **Commit**: YES | Message: `feat(tools): web search + URL fetch`

---

- [x] 13. Config System (YAML Settings + JSON) + OS Keyring for API Keys

  **What to do**:
  - Create `backend/config.py`: Load `~/.ganesh/config.yaml` (create default if not exists), pydantic schema with ALL config fields used across the project:
    ```yaml
    llm:
      provider: openai  # openai | anthropic | google | openrouter | local
      model: gpt-4o-mini
      local:
        base_url: http://localhost:11434/v1
        model: llama3
    voice:
      stt_provider: faster-whisper  # faster-whisper | deepgram | openai
      tts_provider: piper  # piper | elevenlabs | openai
      activation_mode: push-to-talk  # push-to-talk | wake-word | vad
    memory:
      embedding_model: nomic-embed-text
      ollama_url: http://localhost:11434
    personality:
      traits:
        formality: 0.0
        verbosity: 0.0
        warmth: 0.5
        humor: 0.3
        assertiveness: 0.0
      locked: []
    ui:
      theme: dark
      natural_pacing: true
      pacing_speed: 1.0
      text_only_mode: false
    models:
      downloaded: false
    update:
      channel: stable
      auto_check: true
    ```
  - Endpoints: `GET /config` (redacted, no secrets), `PUT /config` (validate + persist), `GET /config/keys/{provider}` (boolean exists, never key), `POST /config/keys/{provider}` (store in keyring), `DELETE /config/keys/{provider}` (remove)
  - Use `keyring` library: service `ganesh`, key `api_key_{provider}`
  - Create `frontend/src/components/settings/SettingsPanel.tsx`: config form + API key entry (password fields)
  - Create `config.yaml.example` template
  - Write tests (TDD): `test_config_load`, `test_config_update`, `test_keyring_store`, `test_keyring_retrieve` (boolean only), `test_keyring_delete`
  - Commit: `feat(config): YAML config + OS keyring for API keys`

  **Must NOT do**: No multi-provider config UI (Task 28), no local LLM config (Task 29)

  **Recommended Agent Profile**:
  - **Category**: `quick` | **Skills**: []
  - **Parallelization**: YES (with 8, 10, 11, 12, 14) | Wave 1 | Blocks: 8, 28 | Blocked By: 3

  **References**:
  - **External**: keyring: `https://pypi.org/project/keyring/`
  - **External**: Pydantic settings: `https://docs.pydantic.dev/latest/usage/settings/`

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_config.py` → PASS (5 tests)
  - [ ] Config persists to YAML, keys stored in keyring (never returned in plaintext)
  - [ ] Default config created on first run

  **QA Scenarios**:
  ```
  Scenario: Config round-trip
    Tool: Bash (curl)
    Steps:
      1. Delete ~/.ganesh/config.yaml (clean state)
      2. Start sidecar → default config created
      3. GET /config → assert defaults
      4. PUT /config {"llm": {"model": "gpt-4o"}} → 200
      5. GET /config → assert model is "gpt-4o"
    Expected Result: Config persists across updates
    Evidence: .sisyphus/evidence/task-13-config-roundtrip.txt

  Scenario: API key stored in keyring, never returned
    Tool: Bash (curl)
    Steps:
      1. POST /config/keys/openai {"key": "sk-test123"}
      2. GET /config/keys/openai → assert {"exists": true}
      3. Assert "sk-test123" NOT in response
    Expected Result: Key stored securely, never in plaintext
    Evidence: .sisyphus/evidence/task-13-keyring.txt
  ```

  **Commit**: YES | Message: `feat(config): YAML config + OS keyring for API keys`

---

- [x] 14. Single-Instance Lock + System Tray + Global Hotkey

  **What to do**:
  - System tray (Tauri core feature, NOT a plugin — enable via `features = ["tray-icon"]` on the `tauri` crate, already done in Task 4):
    - Use `tauri::tray::TrayIconBuilder` in Rust to create tray icon with context menu (Show/Hide, Settings, Quit)
    - Click on tray icon toggles window visibility
  - Global hotkey (`tauri-plugin-global-shortcut` crate):
    - Default: `Ctrl+Shift+G` (configurable), toggles visibility, conflict detection
  - Close button minimizes to tray (configurable), `RunEvent::ExitRequested` confirms quit vs minimize
  - Frontend: SettingsPanel gets hotkey config field + tray behavior toggle
  - Write tests: `test_single_instance`, `test_tray_icon`, `test_hotkey_toggle`
  - Commit: `feat(ui): system tray + global hotkey + single-instance lock`

  **Must NOT do**: No custom tray icon design, no macOS, do NOT use `tauri-plugin-tray` (does not exist — tray is a core feature flag)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high` | **Skills**: []
  - **Parallelization**: YES (with 8, 10, 11, 12, 13) | Wave 1 | Blocks: None | Blocked By: 4

  **References**:
  - **External**: Tauri v2 system tray: `https://v2.tauri.app/learn/system-tray/` — uses `TrayIconBuilder`, NOT a plugin crate
  - **External**: Tauri global shortcut: `https://v2.tauri.app/plugin/global-shortcut/` — crate `tauri-plugin-global-shortcut`
  - **External**: Tauri single-instance: `https://v2.tauri.app/plugin/single-instance/` — crate `tauri-plugin-single-instance`

  **Acceptance Criteria**:
  - [ ] Tray icon visible with menu, `Ctrl+Shift+G` toggles window, hotkey configurable, single-instance prevents double launch

  **QA Scenarios**:
  ```
  Scenario: Global hotkey toggles window
    Tool: Bash (xdotool on Linux, equivalent on Windows)
    Steps:
      1. Launch app, verify window visible
      2. Send synthetic Ctrl+Shift+G
      3. Assert window hidden within 2s
      4. Send again, assert window visible + focused
    Expected Result: Window toggles on hotkey
    Evidence: .sisyphus/evidence/task-14-hotkey.txt

  Scenario: Tray icon present
    Tool: Playwright (Tauri API)
    Steps: 1. Launch app, query tray state, assert icon exists
    Expected Result: Tray icon visible
    Evidence: .sisyphus/evidence/task-14-tray.png
  ```

  **Commit**: YES | Message: `feat(ui): system tray + global hotkey + single-instance lock`

---

- [x] 15. STT Integration (faster-whisper Local + Cloud Fallback)

  **What to do**:
  - Create `backend/voice/stt.py`: `POST /voice/stt` accepting audio file (multipart), returns transcript
  - Local: faster-whisper (CTranslate2 backend, `base` model default, configurable)
  - Cloud fallback: Deepgram (streaming) or OpenAI Whisper API (config-driven)
  - Model path: `~/.ganesh/models/whisper/` (downloaded on first use, Task 22)
  - Register as LLM tool: `transcribe_audio(audio_path)`
  - Write tests (TDD): `test_stt_local` (fixture WAV → transcript), `test_stt_fallback` (mock cloud), `test_stt_no_audio` (400 error)
    - **Fixture WAV generation**: Use Python's `wave` + `struct` modules to generate a synthetic test WAV, OR use `pytest` fixture with `torchaudio`/`soundfile` to synthesize speech-like audio. For CI without audio hardware, mock the STT model and test the API endpoint logic, not the model output.
    - For end-to-end STT accuracy tests: download a known sample WAV (e.g., from `https://github.com/openai/whisper/raw/main/tests/jfk.flac` or similar public domain audio) and assert transcript contains expected keywords.
  - Update NATIVE_DEPS.md: add `faster-whisper`, `ctranslate2`
  - Commit: `feat(voice): STT with faster-whisper + cloud fallback`

  **Must NOT do**: No wake word/VAD (Task 17), no TTS (Task 16), no UI for voice activation

  **Recommended Agent Profile**: `deep` | **Skills**: [] | Wave 2 | Blocks: 17 | Blocked By: 4

  **References**:
  - **External**: faster-whisper: `https://github.com/SYSTRAN/faster-whisper`
  - **External**: OpenAI Whisper API: `https://platform.openai.com/docs/guides/speech`

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_stt.py` → PASS (3 tests)
  - [ ] POST /voice/stt with known fixture audio returns non-empty transcript with expected keywords
  - [ ] Falls back to cloud when local model unavailable (mock test)

  **QA Scenarios**:
  ```
  Scenario: STT transcribes audio file
    Tool: Bash (curl)
    Preconditions: faster-whisper model downloaded, fixture WAV available
    Steps:
      1. Download test fixture: `curl -L -o /tmp/test.wav https://github.com/openai/whisper/raw/main/tests/jfk.flac` (or generate synthetic WAV in test setup)
      2. `curl -F audio=@/tmp/test.wav http://127.0.0.1:$PORT/voice/stt`
      3. Assert transcript JSON is non-empty
      4. If using JFK clip: assert transcript contains "nation" or "ask not" (fuzzy match)
    Expected Result: Accurate transcription of known audio
    Evidence: .sisyphus/evidence/task-15-stt.txt
  ```

  **Commit**: YES | Message: `feat(voice): STT with faster-whisper + cloud fallback`

---

- [x] 16. TTS Integration (Piper Local + Cloud Fallback)

  **What to do**:
  - Create `backend/voice/tts.py`: `POST /voice/tts` accepting `{text}`, returns WAV audio stream
  - Local: Piper TTS (ONNX models, `en_US-amy-medium` default voice, configurable)
  - Cloud fallback: ElevenLabs (best quality) or OpenAI TTS (config-driven)
  - Model path: `~/.ganesh/models/piper/` (downloaded on first use, Task 22)
  - Stream audio chunks for low latency
  - Write tests (TDD): `test_tts_local` (text → WAV with valid RIFF header), `test_tts_fallback`, `test_tts_empty_text` (400)
  - Update NATIVE_DEPS.md: add `piper-tts`, `onnxruntime`
  - Note: PyPI package is `piper-tts`, imported as `piper`. Verify `onnxruntime` native libs collected via `collect_dynamic_libs('onnxruntime')` in PyInstaller spec.
  - Commit: `feat(voice): TTS with Piper + cloud fallback`

  **Must NOT do**: No voice activation (Task 17), no visualizer (Task 18)

  **Recommended Agent Profile**: `deep` | **Skills**: [] | Wave 2 | Blocks: 17 | Blocked By: 4

  **References**:
  - **External**: Piper TTS: `https://github.com/rhasspy/piper`
  - **External**: piper-tts Python: `https://pypi.org/project/piper-tts/`

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_tts.py` → PASS (3 tests)
  - [ ] POST /voice/tts returns WAV with valid RIFF header + non-zero audio data
  - [ ] Falls back to cloud when local model unavailable

  **QA Scenarios**:
  ```
  Scenario: TTS produces audio
    Tool: Bash (curl)
    Steps:
      1. `curl -X POST http://127.0.0.1:$PORT/voice/tts -H "Content-Type: application/json" -d '{"text":"Hello world"}'`
      2. Assert Content-Type in response is audio/wav
      3. Assert response has RIFF header (bytes 0-3 = "RIFF")
      4. Assert content length > 0
    Expected Result: Valid WAV audio produced
    Evidence: .sisyphus/evidence/task-16-tts.wav
  ```

  **Commit**: YES | Message: `feat(voice): TTS with Piper + cloud fallback`

---

- [x] 17. Voice Activation Modes (Push-to-talk, Wake Word, VAD) + Barge-in

  **What to do**:
  - Create `backend/voice/activation.py`: configurable activation mode
    - Push-to-talk: frontend captures audio via Web Audio API `MediaRecorder` + `getUserMedia` (requires microphone permission — configure Tauri CSP + permissions for `microphone`), sends audio chunks to sidecar
    - Wake word: sherpa-onnx wake word detection (configurable model) — runs on backend, frontend streams mic audio via WebSocket
    - Always-on VAD: sherpa-onnx VAD (voice activity detection) — backend processes audio stream, auto-triggers STT on silence
  - Create `backend/voice/barge_in.py`: barge-in state machine
    - If user speaks while TTS is playing: cancel TTS audio, cancel current LLM stream, process new input
    - States: IDLE → LISTENING → PROCESSING → SPEAKING → (barge-in) → LISTENING
  - Frontend: `VoiceActivation.tsx` — mode switcher (settings), push-to-talk button, mic indicator
    - Request microphone permission via `navigator.mediaDevices.getUserMedia({ audio: true })`
    - Configure Tauri CSP to allow `media-src: 'self'` and microphone access
  - Write tests: `test_push_to_talk` (mock audio stream), `test_wake_word` (mock), `test_barge_in` (cancel current speech + LLM)
  - Commit: `feat(voice): activation modes + barge-in state machine`

  **Must NOT do**: No visualizer (Task 18), no wake word model bundling

  **Recommended Agent Profile**: `deep` | **Skills**: [] | Wave 2 | Blocks: None | Blocked By: 15, 16

  **References**:
  - **External**: sherpa-onnx: `https://github.com/k2-fsa/sherpa-onnx` — VAD + wake word
  - **External**: Web Audio API getUserMedia: `https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia`
  - **External**: MediaRecorder API: `https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder`
  - **External**: Tauri permissions/CSP: `https://v2.tauri.app/security/csp/` — must allow microphone access in CSP

  **Acceptance Criteria**:
  - [ ] Push-to-talk mode works (hold key → record → release → transcribe)
  - [ ] Barge-in cancels current TTS + LLM stream when user speaks
  - [ ] Mode is configurable via settings

  **QA Scenarios**:
  ```
  Scenario: Barge-in cancels current speech
    Tool: Bash (curl)
    Steps:
      1. Start TTS for long text
      2. Immediately POST /voice/stt with new audio
      3. Assert TTS audio stream stops within 1s
      4. Assert new STT is processed
    Expected Result: Barge-in interrupts current speech
    Evidence: .sisyphus/evidence/task-17-barge-in.txt
  ```

  **Commit**: YES | Message: `feat(voice): activation modes + barge-in state machine`

---

- [x] 18. Modular Visualizer Plugin Interface + Waveform Implementation

  **What to do**:
  - Create `frontend/src/visualizers/types.ts`: `AudioVisualizer` interface
    ```typescript
    interface AudioVisualizer {
      mount(container: HTMLElement): void;
      feed(data: { fft: Float32Array; waveform: Float32Array; rms: number }): void;
      setStyle(mode: string): void;
      resize(w: number, h: number): void;
      unmount(): void;
    }
    ```
  - Create `frontend/src/visualizers/WaveformViz.ts`: Canvas 2D waveform line implementation
  - Create `frontend/src/components/VisualizerPanel.tsx`: container that mounts active visualizer, receives audio data from TTS stream via Web Audio API `AnalyserNode`
  - Create `frontend/src/visualizers/registry.ts`: plugin registry (register/list visualizers, hot-swap)
  - Write tests: `test_visualizer_interface`, `test_waveform_renders` (canvas pixel variance > 0)
  - Commit: `feat(ui): modular visualizer interface + waveform implementation`

  **Must NOT do**: No holo-face yet (Task 19), no idle animation (Task 32)

  **Recommended Agent Profile**: `visual-engineering` | **Skills**: [] | Wave 2 | Blocks: 19, 32, 37 | Blocked By: 7

  **References**:
  - **External**: Web Audio API AnalyserNode: `https://developer.mozilla.org/en-US/docs/Web/API/AnalyserNode`
  - **External**: Canvas API: `https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API`

  **Acceptance Criteria**:
  - [ ] `AudioVisualizer` interface defined and exported
  - [ ] WaveformViz renders on canvas (pixel variance > 0 when audio playing)
  - [ ] Visualizer registry allows hot-swapping implementations
  - [ ] VisualizerPanel receives audio data from TTS stream

  **QA Scenarios**:
  ```
  Scenario: Waveform visualizer renders during TTS
    Tool: Playwright
    Steps:
      1. Trigger TTS: POST /voice/tts with text
      2. Assert canvas element exists (`[data-testid="visualizer-canvas"]`)
      3. Assert canvas pixel data is non-uniform (variance > 0) during playback
      4. Assert canvas is uniform (variance = 0) when idle
    Expected Result: Visualizer animates during audio playback
    Evidence: .sisyphus/evidence/task-18-waveform.png
  ```

  **Commit**: YES | Message: `feat(ui): modular visualizer interface + waveform implementation`

---

- [x] 19. Additional Visualizer Implementations (Freq Bars, Particles, Holo-face)

  **What to do**:
  - Create `frontend/src/visualizers/FreqBarsViz.ts`: frequency bar graph from FFT bins
  - Create `frontend/src/visualizers/ParticleViz.ts`: particle system (PixiJS) reacting to audio
  - Create `frontend/src/visualizers/HoloFaceViz.ts`: three.js scene with stylized head GLTF, drive blendshapes/vertex displacement by frequency bands (bass → jaw, mids → expression, treble → eye sparkle)
  - Register all in visualizer registry
  - Frontend: visualizer style selector in settings
  - Write tests: `test_freq_bars_renders`, `test_particle_renders`, `test_holo_face_loads` (mock GLTF)
  - Commit: `feat(ui): additional visualizers (freq bars, particles, holo-face)`

  **Must NOT do**: No custom GLTF model creation (use free placeholder), no MilkDrop/butterchurn

  **Recommended Agent Profile**: `visual-engineering` | **Skills**: [] | Wave 2 | Blocks: None | Blocked By: 18

  **References**:
  - **External**: three.js: `https://threejs.org/`
  - **External**: PixiJS: `https://pixijs.com/`
  - **External**: Free GLTF models: `https://poly.pizza/` or `https://sketchfab.com/3d-models/free`

  **Acceptance Criteria**:
  - [ ] All 3 visualizers implement `AudioVisualizer` interface
  - [ ] Visualizer style switchable via settings
  - [ ] Each renders non-uniform pixels when audio is playing

  **QA Scenarios**:
  ```
  Scenario: Switch between visualizer styles
    Tool: Playwright
    Steps:
      1. Trigger TTS
      2. Select "Freq Bars" in settings → assert canvas renders bars
      3. Select "Particles" → assert canvas renders particles
      4. Select "Holo Face" → assert canvas renders 3D scene
    Expected Result: All visualizers render correctly when selected
    Evidence: .sisyphus/evidence/task-19-visualizer-switch.png
  ```

  **Commit**: YES | Message: `feat(ui): additional visualizers (freq bars, particles, holo-face)`

---

- [x] 20. In-App Document Viewer (Images, Text, PDF, JSON) + Annotation

  **What to do**:
  - Create `frontend/src/components/viewer/DocumentViewer.tsx`: modal/panel for viewing files
  - Image viewer: `react-image` or simple `<img>` with zoom/pan
  - Text viewer: syntax-highlighted (Prism.js or Shiki), line numbers
  - PDF viewer: `pdf.js` (react-pdf), page navigation
  - JSON viewer: formatted with collapsible sections (react-json-view or custom)
  - Annotation: assistant can highlight regions (image) or lines (text) to "point out details" — overlay canvas/markers
  - Frontend: `DocumentViewerPanel.tsx` triggered when assistant references a file
  - Write tests: `test_image_viewer`, `test_text_viewer`, `test_pdf_viewer`, `test_json_viewer`, `test_annotation_overlay`
  - Commit: `feat(ui): in-app document viewer with annotation`

  **Must NOT do**: No editing capabilities (view only), no unsupported types (those open in system default)

  **Recommended Agent Profile**: `visual-engineering` | **Skills**: [] | Wave 2 | Blocks: None | Blocked By: 9

  **References**:
  - **External**: react-pdf: `https://github.com/wojtekmaj/react-pdf`
  - **External**: Prism.js: `https://prismjs.com/`
  - **External**: react-json-view: `https://github.com/mac-s-g/react-json-view`

  **Acceptance Criteria**:
  - [ ] Images render with zoom/pan, text renders syntax-highlighted
  - [ ] PDF renders with page navigation, JSON renders formatted
  - [ ] Annotation overlay: assistant can highlight regions/lines via API

  **QA Scenarios**:
  ```
  Scenario: View an image with annotation
    Tool: Playwright
    Steps:
      1. Upload image to sidecar
      2. Assistant references image → viewer opens (`[data-testid="document-viewer"]`)
      3. Assert image visible
      4. Trigger annotation (API: highlight region at x,y,w,h)
      5. Assert annotation overlay visible on image
    Expected Result: Image viewable with annotation overlay
    Evidence: .sisyphus/evidence/task-20-image-viewer.png

  Scenario: View a PDF
    Tool: Playwright
    Steps:
      1. Upload PDF
      2. Viewer opens, assert page 1 renders
      3. Click next page → assert page 2 renders
    Expected Result: PDF pages navigable
    Evidence: .sisyphus/evidence/task-20-pdf-viewer.png
  ```

  **Commit**: YES | Message: `feat(ui): in-app document viewer with annotation`

---

- [x] 21. Theme System (Borders, Background, Chat Style/Color) + Theme Switcher

  **What to do**:
  - Extend `frontend/src/styles/tokens.css`: make all theme properties overridable
  - Create `frontend/src/themes/` directory: theme files (YAML or JSON) defining color overrides
    - `dark.json` (default), `midnight.json`, `carbon.json`, `obsidian.json` (variations)
  - Create `frontend/src/components/settings/ThemeSwitcher.tsx`: dropdown to select theme, live preview
  - Theme affects: borders, background, chat bubble colors, text colors, accent color
  - Persist selected theme in config (via Task 13 config system)
  - Write tests: `test_theme_applies`, `test_theme_persists`, `test_theme_custom_colors`
  - Commit: `feat(ui): theme system + theme switcher`

  **Must NOT do**: No custom theme editor (just predefined themes + config override), no light mode (dark-only per user requirement)

  **Recommended Agent Profile**: `visual-engineering` | **Skills**: [] | Wave 2 | Blocks: None | Blocked By: 7

  **References**:
  - **Pattern**: Task 7 tokens — extend the existing CSS custom property system

  **Acceptance Criteria**:
  - [ ] 4+ predefined dark themes available
  - [ ] Theme switcher changes colors live (no app restart)
  - [ ] Selected theme persists across restarts
  - [ ] Theme affects borders, background, chat bubbles, accent

  **QA Scenarios**:
  ```
  Scenario: Switch theme and verify persistence
    Tool: Playwright
    Steps:
      1. Open settings, select "midnight" theme
      2. Assert body background color changes
      3. Restart app
      4. Assert "midnight" theme still active
    Expected Result: Theme persists across restart
    Evidence: .sisyphus/evidence/task-21-theme-switch.png
  ```

  **Commit**: YES | Message: `feat(ui): theme system + theme switcher`

---

- [x] 22. First-Run Model Download UX (Progress, Checksum, Resume)

  **What to do**:
  - Create `backend/models/manager.py`: download manager for ML models
    - Models: whisper (faster-whisper base), piper voices, embedding model
    - Resumable downloads (HTTP Range), checksum verification (SHA256), retry with backoff
    - Atomic file move (write to `.part`, rename on completion)
    - Progress reporting via WebSocket or SSE to frontend
  - Create `frontend/src/components/setup/ModelDownload.tsx`: first-run setup screen
    - Shows download progress bars for each model
    - Retry button on failure
    - "Skip" option (use cloud fallback, download later)
  - Config: `models.downloaded` flag in config.yaml
  - Write tests: `test_download_resumable`, `test_checksum_verification`, `test_download_failure_recovery`, `test_atomic_move`
  - Commit: `feat(setup): first-run model download with progress + resume`

  **Must NOT do**: No model bundling in minimal installer, no forced download (user can skip + use cloud)

  **Recommended Agent Profile**: `unspecified-high` | **Skills**: [] | Wave 2 | Blocks: 38 | Blocked By: 15, 16

  **References**:
  - **External**: HTTP Range requests: `https://developer.mozilla.org/en-US/docs/Web/HTTP/Range_requests`
  - **External**: faster-whisper models: `https://huggingface.co/Systran` — model repo (e.g., `faster-whisper-base` at `https://huggingface.co/Systran/faster-whisper-base`)
  - **External**: Piper voices: `https://huggingface.co/rhasspy/piper-voices` — voice data files
  - **External**: Ollama embedding models: `https://ollama.com/library/nomic-embed-text`

  **Acceptance Criteria**:
  - [ ] Downloads resume from partial (kill at 50%, restart, continues from 50%)
  - [ ] Checksum verification prevents corrupted models
  - [ ] Progress reported to frontend in real-time
  - [ ] User can skip download (cloud fallback works)

  **QA Scenarios**:
  ```
  Scenario: Download resumes after interruption
    Tool: Bash
    Steps:
      1. Start model download, kill at 50% (check .part file exists)
      2. Restart download
      3. Assert download continues from 50% (not from 0)
      4. Assert .part file renamed to final on completion
    Expected Result: Resumable download works
    Evidence: .sisyphus/evidence/task-22-resume.txt

  Scenario: Corrupted download rejected
    Tool: Bash
    Steps:
      1. Download model
      2. Corrupt the file (flip random bytes)
      3. Restart sidecar, trigger checksum check
      4. Assert corruption detected, re-download offered
    Expected Result: Checksum verification catches corruption
    Evidence: .sisyphus/evidence/task-22-checksum.txt
  ```

  **Commit**: YES | Message: `feat(setup): first-run model download with progress + resume`

---

- [x] 23. Text-Only Mode (Accessibility Parity)

  **What to do**:
  - Ensure ALL functionality is accessible without voice (chat-only mode)
  - Settings: toggle "text-only mode" (disables voice input/output, visualizer shows static/thinking indicator only)
  - When text-only: all responses displayed as text, no TTS audio played
  - Visualizer: shows a gentle "processing" animation instead of waveform when text-only
  - Settings panel: fully navigable via keyboard (Tab, Enter, Esc)
  - Write tests: `test_text_only_disables_voice`, `test_keyboard_navigation_settings`
  - Commit: `feat(a11y): text-only mode with full accessibility parity`

  **Must NOT do**: Do not make text-only a "degraded" mode — it must be fully functional

  **Recommended Agent Profile**: `unspecified-high` | **Skills**: [] | Wave 2 | Blocks: None | Blocked By: 9

  **References**:
  - **External**: WCAG 2.1: `https://www.w3.org/TR/WCAG21/`
  - **External**: Keyboard accessibility: `https://developer.mozilla.org/en-US/docs/Web/Accessibility/Keyboard-navigable_JavaScript_widgets`

  **Acceptance Criteria**:
  - [ ] Text-only mode disables all voice I/O, app remains fully functional
  - [ ] Settings panel navigable via keyboard (Tab forward/back, Enter activate, Esc close)
  - [ ] All chat features work without voice

  **QA Scenarios**:
  ```
  Scenario: Text-only mode is fully functional
    Tool: Playwright
    Steps:
      1. Enable text-only mode in settings
      2. Send a chat message, receive response
      3. Assert response is text (no audio element on page)
      4. Assert visualizer shows static/processing animation (no waveform)
      5. Assert file browsing, web search, memory all work via text
    Expected Result: Full functionality without voice
    Evidence: .sisyphus/evidence/task-23-text-only.png

  Scenario: Keyboard navigation in settings
    Tool: Playwright
    Steps:
      1. Focus settings panel
      2. Tab through all controls
      3. Assert each control receives focus (visible focus indicator)
      4. Enter activates buttons/selects
    Expected Result: Full keyboard navigation
    Evidence: .sisyphus/evidence/task-23-keyboard-nav.png
  ```

  **Commit**: YES | Message: `feat(a11y): text-only mode with full accessibility parity`

---

- [x] 24. Async Task Manager + SQLite Status Store (Start/Status/Cancel/Result)

  **What to do**:
  - Create `backend/tasks/manager.py`: central task registry using asyncio + SQLite persistence
    - `POST /tasks` — start a background task: `{goal, task_type, input}` → `{task_id}`
    - `GET /tasks` — list all tasks with status
    - `GET /tasks/{id}` — get task status: `{status, goal, current_action, result, started_at, completed_at}`
    - `POST /tasks/{id}/cancel` — cancel a running task
    - `GET /tasks/{id}/stream` — SSE stream of task progress updates
  - SQLite schema: `tasks` table (id, goal, status, current_action, result_json, started_at, completed_at, task_type)
  - Task lifecycle: PENDING → RUNNING → COMPLETED/FAILED/CANCELLED
  - Task function registry: map task_type → async function
  - Orphaned task recovery: on sidecar restart, mark RUNNING tasks as INTERRUPTED
  - Write tests (TDD): `test_start_task`, `test_get_status`, `test_cancel_task`, `test_task_persistence`, `test_orphaned_recovery`
  - Commit: `feat(tasks): async task manager with SQLite status store`

  **Must NOT do**: No LangGraph (optional, only if needed later), no sub-agent spawning (Task 25)

  **Recommended Agent Profile**: `deep` | **Skills**: [] | Wave 3 | Blocks: 25 | Blocked By: 3

  **References**:
  - **Pattern**: Custom orchestrator from research: `active_tasks: Dict[task_id, {status, goal, current_action, result}]` + `asyncio.create_task()`

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_task_manager.py` → PASS (5 tests)
  - [ ] Start task returns task_id, status queryable, cancel works, persists across restart
  - [ ] Orphaned tasks (sidecar killed mid-task) marked INTERRUPTED on restart

  **QA Scenarios**:
  ```
  Scenario: Task lifecycle (start → status → complete)
    Tool: Bash (curl)
    Steps:
      1. POST /tasks {"goal": "search for X", "task_type": "web_search", "input": {"query": "test"}}
      2. Assert task_id returned, GET /tasks/{id} shows status "running"
      3. Wait for completion
      4. GET /tasks/{id} shows status "completed" with result
    Expected Result: Full task lifecycle tracked
    Evidence: .sisyphus/evidence/task-24-lifecycle.txt

  Scenario: Cancel a running task
    Tool: Bash (curl)
    Steps:
      1. Start a long-running task
      2. POST /tasks/{id}/cancel
      3. GET /tasks/{id} → assert status "cancelled"
    Expected Result: Task cancelled successfully
    Evidence: .sisyphus/evidence/task-24-cancel.txt

  Scenario: Orphaned task recovery on restart
    Tool: Bash (curl)
    Steps:
      1. Start a long task
      2. Kill sidecar (SIGKILL, not graceful)
      3. Restart sidecar
      4. GET /tasks/{id} → assert status "interrupted"
    Expected Result: Orphaned tasks detected and marked
    Evidence: .sisyphus/evidence/task-24-orphaned.txt
  ```

  **Commit**: YES | Message: `feat(tasks): async task manager with SQLite status store`

---

- [x] 25. Sub-Agent Orchestration (Main Spawns Sub-agents, Parses Results)

  **What to do**:
  - Create `backend/agents/sub_agent.py`: sub-agent runner
    - Each sub-agent has its own LLM context, tools, and goal
    - Sub-agent runs as asyncio task (via Task 24 task manager)
    - Sub-agent reports progress via task status store (current_action updates)
    - Results piped back to main agent for parsing/relaying
  - Create `backend/agents/orchestrator.py`: main agent orchestration logic
    - Main agent decides when to spawn sub-agents (LLM tool: `spawn_sub_agent(goal, task_type)`)
    - Main agent can query sub-agent status without blocking (non-blocking: returns task_id, user asks "how's task X?" → assistant queries status store)
    - Main agent parses sub-agent results: when task completes, result is injected into main agent's context for summarization or relaying
  - Frontend: `TaskPanel.tsx` — shows running/completed background tasks with status, goal, current action, cancel button
  - Write tests: `test_spawn_sub_agent`, `test_query_status_non_blocking`, `test_result_piped_to_main`
  - Commit: `feat(agents): sub-agent orchestration with status queries`

  **Must NOT do**: No LangGraph unless a concrete use case demands it, no plugin-based sub-agents yet (Task 26)

  **Recommended Agent Profile**: `deep` | **Skills**: [] | Wave 3 | Blocks: 26 | Blocked By: 24

  **References**:
  - **Pattern**: Research Pattern A — custom lightweight orchestrator with asyncio.create_task + status store

  **Acceptance Criteria**:
  - [ ] Main agent can spawn sub-agents for background tasks
  - [ ] User can ask "what is task X doing?" → assistant queries status store → relays info without blocking
  - [ ] Sub-agent results are parsed and relayed by main agent when complete
  - [ ] TaskPanel shows all running/completed tasks

  **QA Scenarios**:
  ```
  Scenario: Main agent spawns sub-agent, user queries status
    Tool: Playwright
    Steps:
      1. Send chat: "Search the web for latest Python news and tell me when done"
      2. Assert assistant responds with "I've started a background task" + task_id
      3. Ask "How is the search going?"
      4. Assert assistant relays current status from task store
      5. Wait for completion
      6. Assert assistant summarizes results when task completes
    Expected Result: Non-blocking background task with queryable status
    Evidence: .sisyphus/evidence/task-25-sub-agent.png
  ```

  **Commit**: YES | Message: `feat(agents): sub-agent orchestration with status queries`

---

- [x] 26. Plugin System (importlib + Manifest, Plugins Dir, Tool Registration)

  **What to do**:
  - Create `backend/plugins/loader.py`: dynamic plugin discovery + loading
    - Scan `~/.ganesh/plugins/` for subdirectories containing `manifest.json` + `plugin.py`
    - Manifest schema: `{name, version, description, tools: [{name, description, parameters}], sub_agents: [{type, goal_template}], ui_contributions: [{component, position}]}`
    - Load via `importlib`, register tools with LiteLLM, register sub-agent types with orchestrator
    - Hot-reload: watch plugins dir for changes, reload on modify (or restart sidecar)
  - Create `backend/plugins/registry.py`: registry of loaded plugins + their tools
    - `GET /plugins` — list loaded plugins
    - `POST /plugins/{id}/invoke` — invoke a plugin tool
    - `POST /plugins/reload` — reload all plugins
  - Create example plugin `~/.ganesh/plugins/example/`:
    - `manifest.json`: declares a "note_taker" tool
    - `plugin.py`: implements the tool (saves notes to `~/.ganesh/notes/`)
  - Write tests: `test_plugin_discovery`, `test_plugin_load`, `test_plugin_invoke`, `test_plugin_hot_reload`
  - Commit: `feat(plugins): dynamic import + manifest plugin system`

  **Must NOT do**: No plugin sandboxing (MVP — plugins run in same process), no plugin marketplace

  **Recommended Agent Profile**: `deep` | **Skills**: [] | Wave 3 | Blocks: None | Blocked By: 25

  **References**:
  - **External**: importlib: `https://docs.python.org/3/library/importlib.html`
  - **External**: Python entry points: `https://packaging.python.org/en/latest/specifications/entry-points/`

  **Acceptance Criteria**:
  - [ ] Drop a plugin folder with valid manifest into `~/.ganesh/plugins/` → `GET /plugins` lists it
  - [ ] Plugin tools are callable via `POST /plugins/{id}/invoke`
  - [ ] Plugin tools are registered as LLM tools (assistant can call them)
  - [ ] Example note_taker plugin works end-to-end

  **QA Scenarios**:
  ```
  Scenario: Plugin discovery and invocation
    Tool: Bash (curl)
    Steps:
      1. Copy example plugin to ~/.ganesh/plugins/
      2. POST /plugins/reload
      3. GET /plugins → assert "note_taker" in list
      4. POST /plugins/note_taker/invoke {"input": "remember to buy milk"}
      5. Assert note saved to ~/.ganesh/notes/
      6. Ask assistant via chat: "Take a note: call mom" → assert assistant uses plugin tool
    Expected Result: Plugin loaded, invoked, and integrated with LLM
    Evidence: .sisyphus/evidence/task-26-plugin-invoke.txt
  ```

  **Commit**: YES | Message: `feat(plugins): dynamic import + manifest plugin system`

---

- [x] 27. Conversation History (Search, Export JSON/Markdown, Delete)

  **What to do**:
  - Create `backend/conversations.py`: conversation persistence
    - Store conversations + messages in SQLite (`~/.ganesh/data/conversations.db`): `conversations` table (id, title, profile_id, created_at, updated_at), `messages` table (id, conversation_id, role, content, created_at)
    - `POST /conversations` — create new conversation → conversation_id
    - `GET /conversations` — list conversations (id, title, created_at, message_count)
    - `GET /conversations/{id}` — get full conversation with messages
    - `GET /conversations/search?q={query}` — semantic search: embed query via same embedding model as mem0, search against a LanceDB table containing conversation message embeddings (separate from mem0's memory table). Index each message into LanceDB on creation.
    - `POST /conversations/{id}/export` — export as JSON or Markdown
    - `DELETE /conversations/{id}` — delete conversation + its messages + its LanceDB embeddings
  - Frontend: `ConversationHistory.tsx` — sidebar/panel listing past conversations, search bar, export button, delete
  - Integrate with chat: each chat session is a conversation, auto-titled (first message summary via LLM or first 50 chars)
  - Write tests: `test_create_conversation`, `test_search_conversations`, `test_export_json`, `test_export_markdown`, `test_delete_conversation`
  - Commit: `feat(history): conversation search + export + delete`

  **Must NOT do**: No conversation sharing, no cloud sync

  **Recommended Agent Profile**: `unspecified-high` | **Skills**: [] | Wave 3 | Blocks: None | Blocked By: 10

  **References**:
  - **Pattern**: Task 10 memory layer — reuse LanceDB for semantic search across conversations

  **Acceptance Criteria**:
  - [ ] Conversations persist across restarts
  - [ ] Semantic search finds conversations by content
  - [ ] Export produces valid JSON and Markdown files
  - [ ] Delete removes conversation and its messages

  **QA Scenarios**:
  ```
  Scenario: Search conversation history
    Tool: Bash (curl)
    Steps:
      1. Create conversation, send "I love Python programming"
      2. Create another, send "The weather is nice"
      3. GET /conversations/search?q="programming language"
      4. Assert first conversation in results, second not
    Expected Result: Semantic search finds relevant conversation
    Evidence: .sisyphus/evidence/task-27-search.txt

  Scenario: Export conversation as Markdown
    Tool: Bash (curl)
    Steps:
      1. Create conversation with 2 messages
      2. POST /conversations/{id}/export {"format": "markdown"}
      3. Assert response is valid Markdown with user/assistant messages
    Expected Result: Valid Markdown export
    Evidence: .sisyphus/evidence/task-27-export.md
  ```

  **Commit**: YES | Message: `feat(history): conversation search + export + delete`

---

- [x] 28. Additional LLM Providers (Anthropic, Google, OpenRouter) via LiteLLM

  **What to do**:
  - Extend `backend/llm_router.py`: add Anthropic, Google, OpenRouter providers
  - Each provider needs: API key (from keyring, Task 13), model selection, streaming support
  - Verify LiteLLM streaming + tool calling works identically across providers (note: Anthropic tool format differs — may need adapter shims)
  - Settings UI: provider dropdown (OpenAI, Anthropic, Google, OpenRouter), model dropdown (filtered by provider), API key field
  - Test each provider with: chat, streaming, tool calling
  - Write tests: `test_anthropic_chat`, `test_google_chat`, `test_openrouter_chat`, `test_provider_switching`, `test_tool_calling_anthropic` (adapter if needed)
  - Commit: `feat(llm): multi-provider support (Anthropic, Google, OpenRouter)`

  **Must NOT do**: No local LLM yet (Task 29), no automatic provider fallback (user selects)

  **Recommended Agent Profile**: `unspecified-high` | **Skills**: [] | Wave 3 | Blocks: 29 | Blocked By: 8, 13

  **References**:
  - **External**: LiteLLM providers: `https://docs.litellm.ai/docs/providers`
  - **External**: Anthropic via LiteLLM: `https://docs.litellm.ai/docs/providers/anthropic`
  - **External**: Google Gemini via LiteLLM: `https://docs.litellm.ai/docs/providers/gemini`

  **Acceptance Criteria**:
  - [ ] All 4 providers (OpenAI, Anthropic, Google, OpenRouter) can chat + stream
  - [ ] Tool calling works for all providers (with adapter shims if needed)
  - [ ] Settings UI allows switching provider + model
  - [ ] API keys stored separately per provider in keyring

  **QA Scenarios**:
  ```
  Scenario: Switch from OpenAI to Anthropic
    Tool: Playwright
    Steps:
      1. In settings, select Anthropic provider
      2. Enter Anthropic API key
      3. Send a chat message
      4. Assert response received from Anthropic (check via sidecar logs)
    Expected Result: Provider switching works
    Evidence: .sisyphus/evidence/task-28-provider-switch.png

  Scenario: Tool calling works on Anthropic
    Tool: Bash (curl)
    Steps:
      1. Configure Anthropic provider
      2. Send message that triggers tool call ("list my home directory")
      3. Assert filesystem tool is called and result returned
    Expected Result: Tool calling works across providers
    Evidence: .sisyphus/evidence/task-28-anthropic-tools.txt
  ```

  **Commit**: YES | Message: `feat(llm): multi-provider support (Anthropic, Google, OpenRouter)`

---

- [x] 29. Local LLM Support (OpenAI-compat Endpoints, Ollama)

  **What to do**:
  - Extend `backend/llm_router.py`: add "local" provider type
    - Connect to any OpenAI-compatible endpoint (Ollama, LM Studio, llama.cpp, vLLM, etc.)
    - Config: `llm.local.base_url` (e.g., `http://localhost:11434/v1`), `llm.local.model`
    - No API key needed for local (or empty key)
  - Settings UI: "Local LLM" option with base_url + model fields, "Test Connection" button
  - Model listing: `GET /llm/local/models` — fetch available models from endpoint (`/v1/models`)
  - Embedding model: ensure Ollama integration for mem0 embeddings (Task 10) works with local LLM
  - Write tests: `test_local_llm_chat` (mock Ollama), `test_local_model_listing`, `test_local_no_key`
  - Commit: `feat(llm): local LLM support via OpenAI-compatible endpoints`

  **Must NOT do**: No Ollama bundling (user installs separately), no model management UI

  **Recommended Agent Profile**: `unspecified-high` | **Skills**: [] | Wave 3 | Blocks: None | Blocked By: 28

  **References**:
  - **External**: Ollama OpenAI compatibility: `https://ollama.com/blog/openai-compatibility`
  - **External**: LiteLLM local: `https://docs.litellm.ai/docs/providers/openai_compatible`

  **Acceptance Criteria**:
  - [ ] Can connect to any OpenAI-compatible endpoint (Ollama, LM Studio)
  - [ ] Model listing fetches available models from endpoint
  - [ ] Chat + streaming works with local LLM
  - [ ] No API key required for local

  **QA Scenarios**:
  ```
  Scenario: Connect to Ollama and chat
    Tool: Bash (curl)
    Preconditions: Ollama running locally with a model loaded
    Steps:
      1. PUT /config {"llm": {"provider": "local", "local": {"base_url": "http://localhost:11434/v1", "model": "llama3"}}}
      2. POST /chat {"message": "Hello"}
      3. Assert streaming response received from local model
    Expected Result: Local LLM works via OpenAI-compatible endpoint
    Evidence: .sisyphus/evidence/task-29-local-llm.txt
  ```

  **Commit**: YES | Message: `feat(llm): local LLM support via OpenAI-compatible endpoints`

---

- [x] 30. Personality Trait Matrix (YAML Config) + Dynamic Shifting Engine

  **What to do**:
  - Create `backend/personality/traits.py`: trait matrix system
    - Default traits defined in `config.yaml` under `personality.traits`:
      ```yaml
      personality:
        traits:
          formality: 0.0      # -1.0 (casual) to 1.0 (formal)
          verbosity: 0.0      # -1.0 (concise) to 1.0 (verbose)
          warmth: 0.5         # 0.0 (cold) to 1.0 (warm)
          humor: 0.3          # 0.0 (serious) to 1.0 (playful)
          assertiveness: 0.0  # -1.0 (deferential) to 1.0 (assertive)
      ```
    - All traits clamped to [-1.0, 1.0] or [0.0, 1.0] (prevents runaway drift)
    - Mutation rate cap: max ±0.15 per shift (prevents drastic personality changes)
    - Reset to baseline: `POST /personality/reset`
  - Create `backend/personality/shifter.py`: dynamic context-based shifting
    - Analyze conversation context (user message tone, task type) → compute trait adjustments
    - Shifts are TEMPORARY (session-scoped), not persisted to config
    - User can lock traits: `personality.locked: [formality]` prevents shifting
  - System prompt builder: injects current (baseline + shift) trait values into LLM system prompt
  - Settings UI: `PersonalityPanel.tsx` — sliders for each trait, lock toggles, reset button
  - Write tests: `test_trait_bounds` (values clamped), `test_mutation_rate_cap` (max ±0.15), `test_session_scoped_shift` (not persisted), `test_reset_to_baseline`, `test_locked_traits`
  - Commit: `feat(personality): trait matrix + dynamic shifting engine`

  **Concrete Falsifiable Spec**: Trait values are floats in [-1.0, 1.0] or [0.0, 1.0]. Any shift exceeding ±0.15 from current value is clamped. Shifts are stored per-session and do not modify config.yaml. Locked traits cannot shift. `POST /personality/reset` restores all traits to config baseline.

  **Must NOT do**: No persistent personality drift across sessions, no personality learning from interactions (Task 35 handles proactive learning), no personality without user config

  **Recommended Agent Profile**: `deep` | **Skills**: [] | Wave 4 | Blocks: 34 | Blocked By: 8, 10

  **References**:
  - **Pattern**: Task 13 config system — personality traits stored in config.yaml

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_personality.py` → PASS (5 tests)
  - [ ] Traits clamped to bounds, mutation capped at ±0.15
  - [ ] Shifts session-scoped (config.yaml unchanged)
  - [ ] Locked traits don't shift, reset restores baseline
  - [ ] System prompt includes current trait values

  **QA Scenarios**:
  ```
  Scenario: Trait bounds enforced
    Tool: Bash (curl)
    Steps:
      1. PUT /personality/traits {"formality": 5.0}
      2. GET /personality/traits → assert formality is 1.0 (clamped)
      3. PUT /personality/traits {"formality": -5.0}
      4. Assert formality is -1.0 (clamped)
    Expected Result: Traits clamped to valid bounds
    Evidence: .sisyphus/evidence/task-30-bounds.txt

  Scenario: Mutation rate cap
    Tool: Bash (curl)
    Steps:
      1. Set formality to 0.0
      2. Trigger shift (send formal message)
      3. Assert new formality ≤ 0.15 (max shift)
    Expected Result: No drastic personality changes
    Evidence: .sisyphus/evidence/task-30-mutation-cap.txt

  Scenario: Reset to baseline
    Tool: Bash (curl)
    Steps:
      1. Shift traits via conversation
      2. POST /personality/reset
      3. GET /personality/traits → assert all at config baseline
    Expected Result: Reset works
    Evidence: .sisyphus/evidence/task-30-reset.txt
  ```

  **Commit**: YES | Message: `feat(personality): trait matrix + dynamic shifting engine`

---

- [x] 31. Multiple User Profiles + Shared Bridge Memory Layer

  **What to do**:
  - Create `backend/profiles/manager.py`: profile management
    - `POST /profiles` — create profile: `{name, description, color}` → profile_id
    - `GET /profiles` — list profiles
    - `GET /profiles/{id}` — get profile details
    - `PUT /profiles/{id}` — update profile
    - `DELETE /profiles/{id}` — delete profile (cascade: delete profile's memories, revoke bridge grants)
    - `POST /profiles/{id}/activate` — switch active profile
    - `GET /profiles/active` — get current active profile
  - Create `backend/profiles/bridge.py`: shared bridge memory layer
    - `POST /profiles/bridge/grant` — grant cross-profile access: `{granting_profile_id, receiving_profile_id, memory_id}`. The granting profile allows the receiving profile to query a specific memory.
    - `GET /profiles/bridge/query?receiving_profile={active}&granting_profile={target}&query={semantic_query}` — the active (receiving) profile queries the target (granting) profile's memories, if a grant exists
    - `DELETE /profiles/bridge/grant/{grant_id}` — revoke grant
    - Bridge memory is opt-in per memory (not blanket)
    - Audit log: `bridge_access_log` table (receiving_profile, granting_profile, query, timestamp)
  - Update memory layer (Task 10): all memory operations scoped by profile_id
  - Frontend: `ProfileSwitcher.tsx` — profile dropdown, create/edit/delete, bridge grant management
  - Write tests: `test_create_profile`, `test_profile_isolation` (A's memories not in B), `test_bridge_grant` (A grants → B can query), `test_bridge_revoke`, `test_profile_deletion_cascade`, `test_bridge_audit_log`
  - Commit: `feat(profiles): multiple profiles + shared bridge memory`

  **Must NOT do**: No encryption at rest (MVP — add in Task 40), no auto-grant (explicit per-memory), no blanket access

  **Recommended Agent Profile**: `deep` | **Skills**: [] | Wave 4 | Blocks: None | Blocked By: 10

  **References**:
  - **Pattern**: Task 10 memory layer — extend with profile_id scoping

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_profiles.py` → PASS (6 tests)
  - [ ] Profile A's memories not accessible from Profile B without explicit grant
  - [ ] Bridge grant allows cross-profile semantic query
  - [ ] Grant revocation immediately blocks access
  - [ ] Profile deletion cascades (memories + grants deleted)
  - [ ] Bridge access logged with timestamp + profiles + query

  **QA Scenarios**:
  ```
  Scenario: Cross-profile bridge query with grant
    Tool: Bash (curl)
    Steps:
      1. Create profiles A ("Work") and B ("Personal")
      2. Store memory in A: "Team meeting on Friday at 2pm"
      3. Activate B, query A's memories → assert empty (no grant)
      4. Grant: POST /profiles/bridge/grant {"granting_profile_id": "A", "receiving_profile_id": "B", "memory_id": "<meeting>"}
      5. Query from B: GET /profiles/bridge/query?receiving_profile=B&granting_profile=A&query="meeting schedule"
      6. Assert "Friday at 2pm" in results
    Expected Result: Bridge memory allows cross-profile query with explicit grant
    Evidence: .sisyphus/evidence/task-31-bridge.txt

  Scenario: Profile deletion cascade
    Tool: Bash (curl)
    Steps:
      1. Create profile A with memories + bridge grants to B
      2. DELETE /profiles/{A}
      3. Assert A's memories deleted
      4. Assert grants from A to B deleted
      5. Assert B's memories unaffected
    Expected Result: Clean cascade deletion
    Evidence: .sisyphus/evidence/task-31-cascade.txt

  Scenario: Bridge audit log
    Tool: Bash (curl)
    Steps:
      1. Grant A→B (A grants, B receives), query from B to A
      2. GET /profiles/bridge/audit → assert log entry with receiving_profile=B, granting_profile=A, query, timestamp
    Expected Result: All bridge access logged
    Evidence: .sisyphus/evidence/task-31-audit.txt
  ```

  **Commit**: YES | Message: `feat(profiles): multiple profiles + shared bridge memory`

---

- [x] 32. Ambient Idle Animation (Visualizer Idle State)

  **What to do**:
  - Extend `frontend/src/visualizers/WaveformViz.ts` (and all visualizers): add idle state
    - When no audio is playing and no input for 30 seconds: render gentle "breathing" animation (0.1Hz sine wave modulating opacity/scale)
    - When processing/thinking: render faster pulse (1Hz)
    - When speaking: render active waveform (existing behavior)
  - Visualizer state machine: IDLE (breathing) → THINKING (pulsing) → SPEAKING (active waveform) → IDLE
  - State transitions driven by sidecar events (WebSocket/SSE: "thinking", "speaking", "idle")
  - Write tests: `test_idle_animation` (canvas pixel variance > 0 after 30s idle), `test_state_transitions`
  - Commit: `feat(ui): ambient idle animation for visualizers`

  **Concrete Falsifiable Spec**: After 30s of no audio input/output, visualizer renders a 0.1Hz sine wave with canvas pixel variance > 0 (not static). When sidecar emits "thinking" event, pulse rate increases to 1Hz. When "speaking", renders active waveform. All state transitions complete within 500ms.

  **Must NOT do**: No distracting animation (must be subtle), no CPU-intensive rendering when idle

  **Recommended Agent Profile**: `visual-engineering` | **Skills**: [] | Wave 4 | Blocks: None | Blocked By: 18

  **References**:
  - **Pattern**: Task 18 visualizer interface — extend with idle/thinking/speaking states

  **Acceptance Criteria**:
  - [ ] Visualizer shows breathing animation (pixel variance > 0) after 30s idle
  - [ ] Pulse increases to 1Hz when "thinking" event received
  - [ ] Active waveform when "speaking"
  - [ ] State transitions within 500ms

  **QA Scenarios**:
  ```
  Scenario: Idle animation renders after 30s
    Tool: Playwright
    Steps:
      1. Launch app, wait 31s with no interaction
      2. Capture canvas pixel data at t=31s and t=32s
      3. Assert pixel variance > 0 (not static)
      4. Assert animation frequency ≈ 0.1Hz (slow breathing)
    Expected Result: Gentle idle animation active
    Evidence: .sisyphus/evidence/task-32-idle.png
  ```

  **Commit**: YES | Message: `feat(ui): ambient idle animation for visualizers`

---

- [x] 33. Session Continuity Memory ("Welcome Back" + Temporal Awareness)

  **What to do**:
  - Create `backend/session/continuity.py`: session continuity manager
    - On app launch: retrieve last session's context from memory (mem0)
    - Generate "welcome back" message with temporal awareness: "Welcome back! It's been 3 hours. You were working on [last task]. Want to continue?"
    - Uses mem0 long-term memory to recall: last conversation topic, last task, last interaction timestamp
    - Temporal computation: store `ended_at` as ISO 8601 UTC wall-clock timestamp in SQLite. On next launch, compute delta as `now_utc - ended_at_utc`. Use `time.time()` (epoch) for deltas to handle timezone changes correctly. Do NOT use `time.monotonic()` for cross-restart deltas (it resets between process lifetimes).
  - Store session metadata in SQLite: `sessions` table (id, profile_id, started_at, ended_at, last_topic, last_task_id)
  - On app quit: save session metadata (last topic from conversation, last task status)
  - Frontend: on launch, if returning session detected, show "welcome back" banner with continuation option
  - Write tests: `test_welcome_back_message` (assert contains temporal reference + last topic), `test_epoch_delta` (correct time delta via epoch seconds), `test_first_run_no_welcome` (no welcome on first ever launch)
  - Commit: `feat(session): continuity memory with temporal awareness`

  **Concrete Falsifiable Spec**: On launch, if a previous session exists and ended > 5 minutes ago (computed via `time.time() - session.ended_at_epoch`), assistant generates a message containing: (1) a temporal phrase ("X hours/days ago"), (2) a reference to the last conversation topic, (3) an offer to continue. First-ever launch produces no welcome message. Time deltas use epoch seconds (`time.time()`), not monotonic clock (which resets between process restarts).

  **Must NOT do**: No persistent session state across app reinstall, no "always show welcome" (only on meaningful gap > 5 min)

  **Recommended Agent Profile**: `unspecified-high` | **Skills**: [] | Wave 4 | Blocks: None | Blocked By: 10

  **References**:
  - **Pattern**: Task 10 memory layer — use mem0 for last session context retrieval

  **Acceptance Criteria**:
  - [ ] Returning session (gap > 5 min) shows welcome message with temporal + topic reference
  - [ ] First-ever launch shows no welcome
  - [ ] Time delta computed via epoch seconds (correct across restarts)
  - [ ] User can dismiss or accept continuation

  **QA Scenarios**:
  ```
  Scenario: Welcome back message on return
    Tool: Playwright
    Steps:
      1. Start app, send "I'm working on a Python project"
      2. Quit app
      3. Wait 6 minutes (or mock time)
      4. Relaunch app
      5. Assert welcome message visible: contains temporal phrase + "Python project" reference
    Expected Result: Contextual welcome back message
    Evidence: .sisyphus/evidence/task-33-welcome.png

  Scenario: No welcome on first launch
    Tool: Playwright
    Steps:
      1. Delete ~/.ganesh/data/ (clean state)
      2. Launch app
      3. Assert no welcome back message
    Expected Result: No false welcome on first launch
    Evidence: .sisyphus/evidence/task-33-first-run.png
  ```

  **Commit**: YES | Message: `feat(session): continuity memory with temporal awareness`

---

- [ ] 34. Emotional Context Awareness (Tone Detection + Personality Adjustment)

  **What to do**:
  - Create `backend/personality/emotion.py`: emotional context detection
    - Analyze last 3 user messages for emotional tone (frustration, excitement, sadness, neutral)
    - Use a lightweight sentiment model (e.g., VADER from nltk, or textblob) or LLM-based tone classification
    - Map emotions to trait shifts:
      - Frustration → increase conciseness, decrease verbosity, increase directness
      - Excitement → increase warmth, increase humor
      - Sadness → increase warmth, decrease humor, increase empathy
    - Shifts are bounded by Task 30 mutation cap (±0.15) and respect locked traits
  - Integrate with personality shifter (Task 30): emotion analysis triggers trait adjustments before LLM call
  - Write tests: `test_frustration_detection` (mock frustrated message → concise traits), `test_excitement_detection`, `test_neutral_no_shift`, `test_emotion_respects_locks`, `test_emotion_bounded_by_cap`
  - Commit: `feat(personality): emotional context awareness + trait adjustment`

  **Concrete Falsifiable Spec**: User sends 3 messages with frustration indicators (e.g., "this isn't working", "ugh", "why is this broken"). System detects frustration with confidence > 0.6, shifts verbosity by -0.1 (more concise), warmth by -0.05 (less effusive), assertiveness by +0.1 (more direct). Shifts are bounded by mutation cap and locked traits. Neutral messages produce no shift.

  **Must NOT do**: No persistent emotional state, no emotion detection from voice (text only for MVP), no emotion stored in memory

  **Recommended Agent Profile**: `deep` | **Skills**: [] | Wave 4 | Blocks: None | Blocked By: 30

  **References**:
  - **External**: VADER sentiment: `https://github.com/cjhutto/vaderSentiment`
  - **External**: TextBlob: `https://textblob.readthedocs.io/`
  - **Pattern**: Task 30 trait system — shifts must respect bounds, caps, and locks

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_emotion.py` → PASS (5 tests)
  - [ ] Frustrated messages shift traits toward concise/direct
  - [ ] Excited messages shift traits toward warm/playful
  - [ ] Neutral messages produce no shift
  - [ ] Shifts bounded by mutation cap (±0.15) and locked traits

  **QA Scenarios**:
  ```
  Scenario: Frustration detected, personality shifts to concise
    Tool: Bash (curl)
    Steps:
      1. Set traits to baseline (all 0.0)
      2. Send 3 frustrated messages: "this isn't working", "ugh", "why is this broken"
      3. GET /personality/traits → assert verbosity ≤ -0.05 (shifted toward concise)
      4. Assert assertiveness ≥ 0.05 (shifted toward direct)
    Expected Result: Personality adjusts to user frustration
    Evidence: .sisyphus/evidence/task-34-frustration.txt

  Scenario: Neutral messages produce no shift
    Tool: Bash (curl)
    Steps:
      1. Set traits to baseline
      2. Send 3 neutral messages: "what time is it", "thanks", "ok"
      3. GET /personality/traits → assert all at baseline (no shift)
    Expected Result: No personality drift on neutral input
    Evidence: .sisyphus/evidence/task-34-neutral.txt
  ```

  **Commit**: YES | Message: `feat(personality): emotional context awareness + trait adjustment`

---

- [ ] 35. Proactive Pattern Suggestions (Fluid, Non-Rigid Learning)

  **What to do**:
  - Create `backend/learning/patterns.py`: pattern detection engine
    - Detect recurring user behaviors (e.g., "user always checks weather before meetings", "user creates shopping lists on Sundays")
    - Store detected patterns in mem0 as `type: "pattern"` memories
    - Patterns are FLUID: stored as soft suggestions, not rules. The assistant may offer but must not act without user confirmation.
    - Pattern confidence: 0.0 to 1.0, threshold for suggestion = 0.7 (detected 3+ times)
    - When pattern detected with confidence > 0.7: assistant proactively offers: "I notice you usually [X] before [Y]. Should I [suggest related action]?"
    - User can: accept (pattern becomes stronger), decline (pattern confidence decreases), disable (pattern archived)
  - Create `backend/learning/suggestion_engine.py`: proactive suggestion generator
    - On relevant context, check for matching patterns → generate suggestion
    - Suggestions are injected as a system note in LLM context (not forced)
    - The LLM decides whether to surface the suggestion based on conversation context (FLUID — not rigid)
  - Frontend: suggestion appears as a subtle inline prompt (not a popup, not intrusive)
  - Write tests: `test_pattern_detection` (3 occurrences → confidence > 0.7), `test_pattern_fluidity` (suggestion is offered, not forced), `test_pattern_decline` (confidence decreases), `test_pattern_disable` (archived, not suggested again)
  - Commit: `feat(learning): proactive pattern suggestions (fluid, non-rigid)`

  **Concrete Falsifiable Spec**: System detects a pattern after 3+ occurrences of behavior X preceding behavior Y (confidence > 0.7). On 4th occurrence context, system injects suggestion note into LLM context: "User often does X before Y. Consider offering to help with Y." LLM may or may not surface this (fluid). If user declines, pattern confidence drops by 0.2. If user disables, pattern archived and never suggested again. Patterns NEVER auto-execute — always require user confirmation.

  **Must NOT do**: No auto-execution of suggestions, no rigid rules (always fluid), no patterns that override user's explicit request, no pattern that can't be disabled

  **Recommended Agent Profile**: `deep` | **Skills**: [] | Wave 4 | Blocks: None | Blocked By: 10, 30

  **References**:
  - **Pattern**: Task 10 memory layer — patterns stored as typed memories in mem0

  **Acceptance Criteria**:
  - [ ] `pytest tests/test_patterns.py` → PASS (4 tests)
  - [ ] Pattern detected after 3 occurrences (confidence > 0.7)
  - [ ] Suggestion is offered, not forced (LLM decides to surface)
  - [ ] Decline decreases confidence, disable archives pattern
  - [ ] Pattern never auto-executes

  **QA Scenarios**:
  ```
  Scenario: Pattern detected and offered (not forced)
    Tool: Playwright
    Steps:
      1. User asks about weather 3 times before asking about meetings
      2. On 4th meeting question, assert assistant offers: "I notice you check weather before meetings — should I include it?"
      3. Assert suggestion is phrased as a question, not an action
      4. Assert user can decline without impact on response quality
    Expected Result: Fluid, non-rigid suggestion
    Evidence: .sisyphus/evidence/task-35-pattern.png

  Scenario: Decline decreases confidence, disable archives
    Tool: Bash (curl)
    Steps:
      1. Detect pattern (confidence 0.8)
      2. Decline suggestion → GET /patterns → assert confidence dropped to 0.6
      3. Disable pattern → GET /patterns → assert status "archived"
      4. Trigger context again → assert no suggestion offered
    Expected Result: Pattern learning is fluid and user-controllable
    Evidence: .sisyphus/evidence/task-35-decline.txt
  ```

  **Commit**: YES | Message: `feat(learning): proactive pattern suggestions (fluid, non-rigid)`

---

- [ ] 36. Natural Response Pacing (Typing Indicator, Thinking Pauses)

  **What to do**:
  - Create `frontend/src/components/chat/NaturalPacing.tsx`: response pacing engine
    - Instead of streaming tokens immediately, buffer them and release at natural typing speed (~40-80 chars/sec, configurable)
    - Thinking pauses: before complex responses, show "thinking" indicator for 500ms-2s (duration proportional to response length)
    - Paragraph breaks: brief pause (300ms) at paragraph boundaries
    - Pacing is SUBTLE: not so slow it's annoying, not so fast it feels robotic
  - Setting: "natural pacing" toggle (on/off) + speed multiplier (0.5x, 1x, 2x, instant)
  - Write tests: `test_typing_speed` (output rate ≈ 40-80 cps when pacing on), `test_thinking_pause` (delay before first token), `test_pacing_toggle` (instant when off)
  - Commit: `feat(ui): natural response pacing with thinking pauses`

  **Concrete Falsifiable Spec**: When pacing is ON and speed is 1x: response tokens are released at 40-80 chars/sec (measurable via timestamps). Before first token, a "thinking" indicator shows for 500ms-2s. At paragraph boundaries, 300ms pause. When pacing is OFF: tokens stream immediately (existing behavior). Speed multiplier scales the rate (2x = 80-160 cps).

  **Must NOT do**: No artificial delay on simple responses (only on complex), no delay > 2s (becomes annoying), no delay when pacing off

  **Recommended Agent Profile**: `visual-engineering` | **Skills**: [] | Wave 4 | Blocks: None | Blocked By: 9

  **References**:
  - **Pattern**: Task 9 chat UI — extend with pacing layer over streaming

  **Acceptance Criteria**:
  - [ ] Typing speed 40-80 cps when pacing on (1x)
  - [ ] Thinking indicator 500ms-2s before complex responses
  - [ ] 300ms pause at paragraph boundaries
  - [ ] Instant streaming when pacing off
  - [ ] Speed multiplier scales rate correctly

  **QA Scenarios**:
  ```
  Scenario: Natural pacing produces readable typing speed
    Tool: Playwright
    Steps:
      1. Enable natural pacing (1x)
      2. Send message requiring a 100+ char response
      3. Measure time between first and last token
      4. Assert chars/sec is between 40-80
    Expected Result: Natural typing speed
    Evidence: .sisyphus/evidence/task-36-pacing.txt

  Scenario: Instant when pacing off
    Tool: Playwright
    Steps:
      1. Disable natural pacing
      2. Send message
      3. Assert tokens appear immediately (no measurable delay between chunks)
    Expected Result: Instant streaming when pacing off
    Evidence: .sisyphus/evidence/task-36-instant.txt
  ```

  **Commit**: YES | Message: `feat(ui): natural response pacing with thinking pauses`

---

- [ ] 37. Thinking Indicator (Visualizer Processing State)

  **What to do**:
  - Extend visualizer state machine (Task 32): THINKING state renders a distinct visual pattern
    - Waveform: slow, even pulse (distinct from idle breathing — faster, more regular)
    - Freq bars: gentle ascending cascade
    - Holo face: eyes glow, subtle "processing" expression
    - Particles: slow inward spiral
  - Sidecar emits "thinking" event (WebSocket/SSE) when LLM call starts, "speaking" when TTS begins, "idle" when done
  - Frontend: `ThinkingIndicator.tsx` — optional text indicator ("Ganesh is thinking...") below visualizer (configurable, subtle)
  - Write tests: `test_thinking_visual_state` (distinct from idle), `test_state_transition_on_llm_start`
  - Commit: `feat(ui): thinking indicator for visualizer processing state`

  **Concrete Falsifiable Spec**: When sidecar emits "thinking" event, visualizer transitions from IDLE to THINKING state within 500ms. THINKING visual is distinct from IDLE (faster pulse rate, different color/intensity). When "speaking" event emitted, transitions to SPEAKING. When "idle" event, returns to IDLE. All transitions logged and testable via state query.

  **Must NOT do**: No verbose "processing" text (subtle indicator only), no blocking on thinking state

  **Recommended Agent Profile**: `visual-engineering` | **Skills**: [] | Wave 4 | Blocks: None | Blocked By: 18

  **References**:
  - **Pattern**: Task 32 ambient idle — extend state machine with THINKING visual

  **Acceptance Criteria**:
  - [ ] THINKING state visual is distinct from IDLE
  - [ ] State transitions within 500ms of sidecar event
  - [ ] Optional text indicator configurable (on/off)

  **QA Scenarios**:
  ```
  Scenario: Thinking indicator activates on LLM call
    Tool: Playwright
    Steps:
      1. Send a chat message
      2. Assert visualizer transitions to THINKING state within 500ms
      3. Assert THINKING visual is distinct from IDLE (different pulse rate/intensity)
      4. When response starts streaming, assert transition to SPEAKING
    Expected Result: Visual feedback during processing
    Evidence: .sisyphus/evidence/task-37-thinking.png
  ```

  **Commit**: YES | Message: `feat(ui): thinking indicator for visualizer processing state`

---

- [ ] 38. Installer Variants (Minimal + Full with Pre-bundled Models)

  **What to do**:
  - Create two PyInstaller build configs:
    - `pyinstaller-minimal.spec`: No models bundled, first-run download (Task 22)
    - `pyinstaller-full.spec`: Pre-bundles whisper base model + piper default voice + embedding model in `dist/models/`
  - For Tauri, use a single `tauri.conf.json` but two build scripts:
    - `scripts/build-minimal.sh` / `scripts/build-minimal.ps1`: builds with minimal PyInstaller spec
    - `scripts/build-full.sh` / `scripts/build-full.ps1`: builds with full PyInstaller spec, copies models to `dist/models/` before Tauri bundling
  - GitHub Actions: build both variants for Windows + Linux, upload as separate release artifacts
  - Update CI workflow: add `build-minimal` and `build-full` jobs (matrix: OS × variant)
  - Write tests: `test_minimal_no_models` (no .onnx/.bin model files in dist), `test_full_has_models` (models present in dist/models/)
  - Commit: `feat(installer): minimal + full installer variants`

  **Must NOT do**: No macOS builds, no model download during build (full variant bundles pre-downloaded)

  **Recommended Agent Profile**: `deep` | **Skills**: [] | Wave 5 | Blocks: 39 | Blocked By: 22

  **References**:
  - **External**: Tauri bundling: `https://v2.tauri.app/distribute/`
  - **External**: PyInstaller multi-spec: `https://pyinstaller.org/en/stable/spec-files.html`

  **Acceptance Criteria**:
  - [ ] Minimal installer: no models in dist, < 100MB
  - [ ] Full installer: models present in dist, works offline immediately
  - [ ] Both variants build on Windows + Linux in CI

  **QA Scenarios**:
  ```
  Scenario: Minimal installer has no bundled models
    Tool: Bash
    Steps:
      1. Build minimal variant
      2. Assert no .onnx or model files in dist/models/
      3. Assert installer size < 100MB
    Expected Result: Clean minimal installer
    Evidence: .sisyphus/evidence/task-38-minimal.txt

  Scenario: Full installer works offline immediately
    Tool: Bash
    Steps:
      1. Build full variant
      2. Assert model files present in dist/models/
      3. Launch app with network disabled
      4. Assert STT + TTS work (using bundled models)
    Expected Result: Full offline functionality
    Evidence: .sisyphus/evidence/task-38-full.txt
  ```

  **Commit**: YES | Message: `feat(installer): minimal + full installer variants`

---

- [ ] 39. Auto-Update (Tauri Updater Plugin)

  **What to do**:
  - Integrate `tauri-plugin-updater` (crate `tauri-plugin-updater = "2"`):
    - checks for updates on launch + manual "Check for Updates" in settings
  - Update flow: download new installer → verify signature → prompt user → install on quit
  - Since sidecar is bundled, update downloads full installer (100MB+ minimal, 500MB+ full)
  - Config: `update.channel` (stable, beta), `update.auto_check` (boolean)
  - Frontend: `UpdateNotification.tsx` — banner when update available, progress bar during download
  - Write tests: `test_update_check`, `test_update_download_progress`, `test_update_cancel`
  - Commit: `feat(update): auto-update with Tauri updater plugin`

  **Must NOT do**: No delta updates (full replace only), no forced updates (always user-initiated)

  **Recommended Agent Profile**: `unspecified-high` | **Skills**: [] | Wave 5 | Blocks: None | Blocked By: 38

  **References**:
  - **External**: Tauri updater: `https://v2.tauri.app/plugin/updater/`

  **Acceptance Criteria**:
  - [ ] App checks for updates on launch (if auto-check enabled)
  - [ ] Manual "Check for Updates" in settings
  - [ ] Download progress shown, user can cancel
  - [ ] Update installs on next app quit

  **QA Scenarios**:
  ```
  Scenario: Update notification appears
    Tool: Playwright
    Steps:
      1. Mock update endpoint with higher version
      2. Launch app
      3. Assert update banner appears ("Update available")
      4. Click "Download" → assert progress bar visible
    Expected Result: Update flow works
    Evidence: .sisyphus/evidence/task-39-update.png
  ```

  **Commit**: YES | Message: `feat(update): auto-update with Tauri updater plugin`

---

- [ ] 40. Error Recovery (Sidecar Crash, Reconnect, Corrupted Memory, Disk Full)

  **What to do**:
  - Sidecar crash recovery:
    - Frontend detects sidecar death (HTTP 502/connection drop on health check)
    - Shows "Reconnecting..." state with auto-restart attempt (max 3 retries, 2s apart)
    - If restart fails, shows "Assistant offline" with manual restart button
    - Conversation history persisted client-side, can resume from last message
  - Corrupted memory recovery:
    - On startup, LanceDB schema version check + integrity probe
    - If corrupted: prompt "Memory appears corrupted. Reset or attempt repair?"
    - Repair: re-index from JSON backup (if available)
    - Reset: archive corrupted DB, start fresh
  - Disk full during model download:
    - Detect disk space before download, warn if < 2x model size
    - On ENOSPC: pause download, show "Disk full" message, allow cleanup or cancel
  - API key rotation/revocation:
    - LLM call 401 → show "API key invalid" in settings, prompt re-entry
    - Sidecar does NOT crash, returns user-friendly error to chat
  - Write tests: `test_sidecar_reconnect`, `test_corrupted_memory_detection`, `test_disk_full_handling`, `test_api_key_invalid_graceful`
  - Commit: `feat(recovery): error recovery for crashes, corruption, disk full, key rotation`

  **Must NOT do**: No silent failures (all errors surfaced to user), no data loss (always offer recovery before destructive actions)

  **Recommended Agent Profile**: `deep` | **Skills**: [] | Wave 5 | Blocks: None | Blocked By: 3, 4, 10

  **References**:
  - **Pattern**: Task 5 Playwright integration — test sidecar restart scenario
  - **Pattern**: Task 10 memory layer — integrity check on startup

  **Acceptance Criteria**:
  - [ ] Sidecar crash: frontend shows reconnecting, auto-restarts (3 retries), offers manual restart
  - [ ] Corrupted memory: detected on startup, user offered repair or reset
  - [ ] Disk full: detected, download paused with message
  - [ ] Invalid API key: graceful error in chat, no sidecar crash

  **QA Scenarios**:
  ```
  Scenario: Sidecar crash triggers reconnect
    Tool: Playwright
    Steps:
      1. Launch app, verify healthy
      2. Kill sidecar process (SIGKILL)
      3. Assert frontend shows "Reconnecting..." within 2s
      4. Assert auto-restart attempts (sidecar relaunches)
      5. Assert health check passes after restart
    Expected Result: Automatic recovery from crash
    Evidence: .sisyphus/evidence/task-40-reconnect.png

  Scenario: Corrupted memory detected on startup
    Tool: Bash
    Steps:
      1. Corrupt LanceDB files (flip random bytes)
      2. Launch app
      3. Assert corruption detected, prompt shown
      4. Choose "Reset" → assert fresh memory store created
    Expected Result: Graceful handling of corruption
    Evidence: .sisyphus/evidence/task-40-corruption.txt

  Scenario: Invalid API key doesn't crash
    Tool: Bash (curl)
    Steps:
      1. Set invalid API key
      2. POST /chat {"message": "hello"}
      3. Assert response contains error message (not 500 crash)
      4. Assert sidecar still healthy (GET /health → 200)
    Expected Result: Graceful API key error
    Evidence: .sisyphus/evidence/task-40-key-error.txt
  ```

  **Commit**: YES | Message: `feat(recovery): error recovery for crashes, corruption, disk full, key rotation`

---

- [ ] 41. Bundle Size Budget Enforcement + Final CI Hardening

  **What to do**:
  - Add CI step: after build, check bundle size
    - Sidecar binary: `du -sh dist/ganesh-sidecar` → warn if > 150MB, fail if > 250MB
    - Minimal installer: warn if > 100MB, fail if > 150MB
    - Full installer: warn if > 1GB, fail if > 1.5GB
  - Add `ast_grep_search` CI step: scan frontend for hardcoded ports
    - Patterns: `localhost:\d+`, `127.0.0.1:\d+`, `0.0.0.0:\d+` in frontend source files
    - Exception: allow `127.0.0.1` without port (e.g., in comments/docs), but ANY literal port number is forbidden
    - Fail CI if any hardcoded port found (must use ephemeral port from Tauri)
    - Use regex pattern: `(localhost|127\.0\.0\.1|0\.0\.0\.0):\d{2,5}` on `frontend/src/**/*.ts` and `frontend/src/**/*.tsx`
  - Add lint step: ruff (Python) + eslint (TS) in CI
  - Add type check: mypy (Python) + tsc --noEmit (TS) in CI
  - Final CI matrix: Windows + Linux, all checks (lint, type, test, build, bundle size, port scan)
  - Write test: `test_no_hardcoded_ports` (grep frontend for port patterns)
  - Commit: `chore(ci): bundle size budget + hardcoded port check + lint + type check`

  **Must NOT do**: No warnings suppressed, no `as any` or `@ts-ignore` without justification comment

  **Recommended Agent Profile**: `quick` | **Skills**: [] | Wave 5 | Blocks: None | Blocked By: 2

  **References**:
  - **External**: ruff: `https://docs.astral.sh/ruff/`
  - **External**: eslint: `https://eslint.org/`
  - **Tool**: `ast_grep_search` for port pattern detection

  **Acceptance Criteria**:
  - [ ] CI checks: lint, type, test, build, bundle size, port scan — all on Windows + Linux
  - [ ] Bundle size warnings + failures enforced
  - [ ] No hardcoded ports in frontend (CI fails if found)

  **QA Scenarios**:
  ```
  Scenario: CI enforces bundle size
    Tool: Bash (CI)
    Steps:
      1. Build sidecar binary
      2. Run `du -sh dist/ganesh-sidecar`
      3. Assert size ≤ 250MB (CI passes)
    Expected Result: Bundle within budget
    Evidence: .sisyphus/evidence/task-41-bundle-size.txt

  Scenario: No hardcoded ports in frontend
    Tool: Bash (grep)
    Steps:
      1. Run: `grep -rnE '(localhost|127\.0\.0\.1|0\.0\.0\.0):[0-9]{2,5}' frontend/src/`
      2. Assert no matches found (exit code 1 from grep = no matches = pass)
    Expected Result: All ports are dynamic (no hardcoded port numbers)
    Evidence: .sisyphus/evidence/task-41-no-hardcoded-ports.txt
  ```

  **Commit**: YES | Message: `chore(ci): bundle size budget + hardcoded port check + lint + type check`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, curl endpoint, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `pytest` + `vitest` + `playwright test`. Review all changed files for: `as any`/`@ts-ignore`, empty catches, console.log in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names. Verify no hardcoded ports (`grep -rnE '(localhost|127\.0\.0\.1|0\.0\.0\.0):[0-9]{2,5}' frontend/src/` returns nothing). Verify no ML models bundled in minimal installer.
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high` (+ `playwright` skill if UI)
  Start from clean state on Windows + Linux. Execute EVERY QA scenario from EVERY task — follow exact steps, capture evidence. Test cross-task integration. Test edge cases: empty state, invalid input, rapid actions, sidecar crash, two instances, large file drag-drop, offline mode. Save to `.sisyphus/evidence/final-qa/`.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N tested] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff (git log/diff). Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance. Detect cross-task contamination. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Convention**: Conventional Commits with scope: `feat(voice):`, `feat(memory):`, `feat(ui):`, `fix(sidecar):`, `test(memory):`, `docs:`, `chore(ci):`, `refactor(orchestration):`
- **TDD pairs**: `test: add <behavior> test (red)` → `feat: implement <behavior> (green)` OR single `feat: <behavior> (with tests)` for small implementations
- **Wave completion**: `chore(wave-N): mark complete — green CI on win/linux`
- **No "wip" or "misc" commits** — if you can't name it, split it
- **Each commit leaves repo in buildable + testable state**
- **Sidecar spec changes** (NATIVE_DEPS.md + .spec) are ALWAYS a separate commit from feature code

---

## Success Criteria

### Verification Commands
```bash
# Sidecar health (both OSes)
curl http://127.0.0.1:$PORT/health  # Expected: {"status":"ok"}

# Python tests
pytest tests/  # Expected: all pass

# Frontend tests
cd frontend && vitest  # Expected: all pass

# Integration tests (real app + stub LLM)
playwright test  # Expected: all pass

# Frozen binary native deps
./dist/ganesh-sidecar --check-imports  # Custom flag: imports all registered native deps, exit 0/1

# CI matrix
# GitHub Actions: windows-latest + ubuntu-latest both green

# Bundle size
du -sh dist/  # Sidecar binary ≤ 150MB (warn), ≤ 250MB (fail)
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass (pytest + vitest + Playwright)
- [ ] Green CI on Windows + Linux
- [ ] `curl /health` returns ok on both OSes
- [ ] No hardcoded ports in frontend
- [ ] No ML models in minimal installer
- [ ] Single-instance lock works
- [ ] All lifelike features have falsifiable specs and pass programmatic assertions
