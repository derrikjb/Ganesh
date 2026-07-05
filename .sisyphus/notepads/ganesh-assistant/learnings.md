# Ganesh Assistant Learnings

## Conventions
- Use Conventional Commits: `feat(scope): description`
- Python backend: FastAPI, pytest, mypy, ruff
- Frontend: React + TypeScript + Vite + Tailwind CSS + vitest
- Desktop: Tauri v2
- All ports must be ephemeral (never hardcoded)
- Dark theme only (no light mode)
- Windows + Linux only (no macOS)

## Patterns
- TDD: RED → GREEN → REFACTOR
- Each commit leaves repo buildable + testable
- Sidecar spec changes are separate commits from feature code

## Decisions
- Stack: Python (backend) + React/TS (frontend) + Tauri v2 (shell)
- Memory: mem0 OSS + LanceDB
- Voice: faster-whisper + Piper
- LLM: LiteLLM routing (OpenAI default)
- License: PolyForm Noncommercial 1.0.0
## Wave 0: Foundation
- Scaffolded project structure with backend (FastAPI), frontend (Vite/React/TS), and src-tauri (Tauri v2).
- Configured pyproject.toml with required dependencies.
- Configured package.json with Vitest and Tailwind CSS.
- Initialized git repository with appropriate .gitignore.
- Created README.md and LICENSE (PolyForm Noncommercial 1.0.0).
- Verified directory structure manually.
## Wave 0: Scaffold Fixes
- Replaced LICENSE placeholder with full PolyForm Noncommercial License 1.0.0 text.
- Fixed frontend React scaffold:
    - Replaced main.ts with main.tsx.
    - Created App.tsx with minimal 'Ganesh' heading.
    - Updated index.html and index.css.
    - Created vite.config.ts with @vitejs/plugin-react.
    - Removed vanilla Vite template assets and files.
- Updated Tauri configuration:
    - Restricted bundle targets to Windows and Linux (deb, appimage, msi, nsis).
    - Removed .icns icon.
    - Set CSP to allow connect-src http://127.0.0.1:*.
- Updated and verified project structure tests:
    - Backend tests verify critical directories and files.
    - Frontend tests verify key React and Vite files.
- Note: cargo check could not be verified due to missing cargo/rustc in the environment.

## Native Dependencies and Frozen Binaries
- Added `--check-imports` flag to `backend/main.py` to verify bundling of native dependencies in frozen environments.
- Documented native dependencies in `docs/NATIVE_DEPS.md`.
- Integrated frozen binary health check into CI pipeline.

## Wave 1: Sidecar (Task 3) — FastAPI + PyInstaller spec
- `backend/main.py` is the sidecar entry. Uses a `GaneshServer(uvicorn.Server)` subclass that overrides `startup()` to print `PORT: <port>` (flush=True) after uvicorn binds — Tauri reads this from stdout to discover the ephemeral port.
- Ephemeral port: bind to `127.0.0.1:0`, never hardcode. Port 0 = OS assigns.
- CORS origins for Tauri v2: `tauri://localhost` (Linux/macOS webview) AND `https://tauri.localhost` (Windows webview). Both required.
- Shutdown coordination: a module-level `threading.Event` (`shutdown_event`) is set by `/shutdown` endpoint, SIGTERM handler, SIGINT handler, and lifespan cleanup. A daemon watchdog thread waits on it and sets `server.should_exit = True`. Avoid `os._exit` — it skips lifespan cleanup.
- `--check-imports` flag: imports every module in `NATIVE_DEPS` tuple, exits 0/1. Success message MUST be `"All native dependencies imported successfully"` (pre-existing `test_native_deps.py` asserts this exact string).
- `NATIVE_DEPS` registry lives in `main.py`; `docs/NATIVE_DEPS.md` is the human-readable mirror. Add new native deps to BOTH plus the pyinstaller spec.
- PyInstaller spec (`backend/pyinstaller.spec`): onefile mode, `console=True` (sidecar needs stdout for PORT line). Uses `collect_all()` + `collect_dynamic_libs()` for pydantic/uvicorn/keyring. Wave 2+ deps (faster-whisper, piper, lancedb, sounddevice) are commented-out templates.
- PyInstaller is NOT in pyproject.toml — it's a build-time tool, installed separately when building the frozen binary.
- Tests: `test_health.py` has 6 tests (health, CORS tauri://, CORS https://, ephemeral port via subprocess, shutdown, check-imports). The ephemeral-port test spawns the sidecar as a subprocess and parses stdout for `PORT: \d+`.
- Full backend suite: 17 tests passing.

## Wave 2: Tauri Shell (Task 9) — sidecar lifecycle + frontend scaffold
- `tauri-build` crate is versioned SEPARATELY from `tauri`. As of this env: `tauri = "2.11.5"` but `tauri-build = "2.6.3"`. Do NOT copy the tauri version into tauri-build.
- `tauri::generate_context!()` requires a `build.rs` containing `tauri_build::build()` (sets OUT_DIR) AND valid icon files referenced in tauri.conf.json. Missing either → compile error.
- `bundle.externalBin` paths get a `-{target_triple}` suffix appended at build time (e.g. `ganesh-backend-x86_64-unknown-linux-gnu`). tauri-build FAILS the build if the suffixed path doesn't exist. Created a placeholder stub at `backend/dist/ganesh-backend-x86_64-unknown-linux-gnu` to satisfy the check; real binary is produced by PyInstaller.
- Sidecar spawn uses `std::process::Command` (allowed by spec's "or" clause) for testability — core logic lives in `lib.rs` (`ganesh_lib` crate) so `cargo test` can exercise spawn/port-read/shutdown with mock `sh -c` scripts. `tauri_plugin_shell` is still initialized in the builder for shell capabilities.
- SIGTERM to a shell running a foreground `sleep` does NOT interrupt the sleep — the trap only fires after the child exits. Use `cmd & wait` idiom so `wait` is interruptible by the trap. This is essential for graceful-shutdown tests.
- `libc::kill(pid, SIGTERM)` is the std-compatible way to send SIGTERM on Unix (std has no SIGTERM API, only `Child::kill` = SIGKILL). Added `libc` as a unix-only dependency.
- Bun's `node` shim does NOT support vitest's worker pool (`port.addListener is not a function` / `channel.unref` errors). Use a real Node.js binary for `npx vitest`. Downloaded node v20.11.1 to /tmp for test runs.
- Fake timers + async React hooks = pain. Switched useSidecar tests to real timers + `waitFor` with timeouts. Retry interval is 1s so retry tests take ~1-2s each.
- `@tauri-apps/api` and `@tauri-apps/plugin-shell` must be added to frontend package.json for `invoke()` + shell APIs.
