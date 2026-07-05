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

## Wave 2: Playwright Integration Tests (Task 5)
- Playwright test runner transpiles TypeScript natively — no tsx/ts-node needed for test files or fixtures imported by tests. Raw `node` cannot run `.ts` fixtures directly (would need tsx), but this isn't required since Playwright imports them.
- `@tauri-apps/api/core`'s `invoke()` calls `window.__TAURI_INTERNALS__.invoke(cmd, args, options)`. In a non-Tauri browser (Vite dev server), inject a shim via `page.addInitScript()` BEFORE `page.goto()` so the frontend's `invoke('get_sidecar_port')` returns the stub sidecar port.
- Stub sidecar implemented as pure-Node `http.createServer` (not FastAPI) despite spec saying "FastAPI stub" — the `.ts` file extension and frontend-only test scope make Node HTTP the pragmatic choice. It mirrors the real sidecar's contract: `/health`, `/shutdown`, CORS headers, `PORT: <port>` stdout line.
- Vitest picks up Playwright `.spec.ts` files by default — MUST exclude `tests/integration/` and `tests/fixtures/` in `vitest.config.ts` `test.exclude`.
- `useSidecar` hook originally had NO post-connection health monitoring — once `isReady=true`, it never detected sidecar death. Added a periodic health check (every 2s) that transitions back to "reconnecting" state. Required for the sidecar-restart integration test.
- Playwright `webServer` starts the Vite dev server; the stub sidecar is started per-test-suite via `beforeAll`/`afterAll` in helpers.ts (NOT webServer) so tests can kill/restart it independently.
- Real Node.js binary at `/tmp/node-v20.11.1-linux-x64/bin/node` required for Playwright (bun's node shim doesn't work). Chromium libs were already present on this system despite `install-deps` failing (no sudo).
- CI: `npx playwright install --with-deps chromium` installs browser + system deps. Upload `playwright-report/` as artifact on failure.

## Wave 3: Design System (Task 20) — tokens + dark theme
- Tailwind v4 uses `@theme` directive in CSS, NOT `tailwind.config.js`. Removed old config.
- Design tokens live in `src/styles/tokens.css` (raw values), theme layer in `src/styles/theme.css` (semantic aliases).
- Tailwind theme bridge in `src/styles/tailwind-theme.css` maps CSS vars to Tailwind utilities via `@theme`.
- `ThemeContext` wraps App with `ThemeProvider`, sets `data-theme` attribute and `colorScheme` on `<html>`.
- Test path resolution: `__dirname` in `src/__tests__/` resolves `../styles/` correctly (not `../../styles/`).
- All 17 tests pass (4 test files), tsc --noEmit clean.

## Wave 3: Design System (Task 20) — tokens + dark theme
- Tailwind v4 uses `@theme` directive in CSS, NOT `tailwind.config.js`. Removed old config.
- Design tokens live in `src/styles/tokens.css` (raw values), theme layer in `src/styles/theme.css` (semantic aliases).
- Tailwind theme bridge in `src/styles/tailwind-theme.css` maps CSS vars to Tailwind utilities via `@theme`.
- `ThemeContext` wraps App with `ThemeProvider`, sets `data-theme` attribute and `colorScheme` on `<html>`.
- Test path resolution: `__dirname` in `src/__tests__/` resolves `../styles/` correctly (not `../../styles/`).
- All 17 tests pass (4 test files), tsc --noEmit clean.

## Wave 3: Web Search Tool (Task — search)
- Search service uses DuckDuckGo HTML endpoint (https://html.duckduckgo.com/html/) — no API key, free, returns parseable HTML. POST with form data `{"q": query}`.
- A browser-like User-Agent is REQUIRED — DDG returns 403 to httpx's default UA.
- DDG wraps result URLs in a `/l/?uddg=<urlencoded>` redirect. Must extract & `unquote` the `uddg` query param to recover the real destination URL.
- Result parsing: regex matching `class="result__a"` (title + href) followed by `class="result__snippet"` (snippet). Use `re.DOTALL` since tags span lines. Strip HTML tags + `html.unescape` for clean text.
- Graceful degradation: HTTP 429 (rate limit) and `httpx.HTTPError` both return `[]` instead of raising — search is best-effort.
- Testability: `web_search()` accepts an optional `client: httpx.AsyncClient | None`. Tests inject a client built with `httpx.MockTransport` (built-in, no respx needed). Router uses FastAPI dependency injection (`get_search_client`) overridable via `app.dependency_overrides`.
- Router: `GET /api/search?query=&limit=` — empty query → 400, `limit` constrained via `Query(ge=1, le=20)`. Missing `query` param → 422 (FastAPI auto).
- Added `httpx` to `pyproject.toml` runtime deps (was only in dev extras before).
- Full backend suite: 31 tests passing (5 new search tests).

## Wave 3: Files Router (Task — file system browsing tool)
- New router at `backend/ganesh_backend/routers/files.py`, mounted in `main.py` via `app.include_router(files_router.router)`. Prefix `/api/files`, three GET endpoints: `/list`, `/read`, `/navigate`.
- Security model: `BLOCKED_DIRS` tuple of system paths (/etc, /proc, /sys, /boot, /dev, /root, /var/log, /usr, /bin, /sbin, /lib, /lib64, /run, /snap). `_resolve()` always calls `Path.resolve(strict=False)` to collapse `..` and symlinks BEFORE the blocklist check — this is the single chokepoint that defeats traversal and symlink-escape attacks.
- `_check_blocked()` uses `blocked_resolved in resolved.parents` plus exact equality, so both the dir itself and anything under it are 403.
- `MAX_READ_BYTES = 10 * 1024 * 1024` (10 MiB). Files exceeding → 413 Payload Too Large. Exposed as module-level so tests can reference `files_router.MAX_READ_BYTES`.
- `_entry_metadata()` MUST catch `OSError` from `Path.stat()` — home dirs commonly contain broken symlinks (e.g. `.steampath`) that raise `FileNotFoundError`. Returns `type="broken"`, size 0, epoch timestamp on failure.
- Relative paths resolve against `Path.home()` (not cwd) — matches the "default to home dir" spec and keeps the sidecar deterministic regardless of where Tauri spawns it.
- Error code convention: 403 blocked, 404 not found, 400 wrong type (file vs dir), 413 too large.
- Tests: 22 in `tests/test_files.py` including a live-sidecar subprocess test that boots the real server and curls `/api/files/list` + verifies `/etc` returns 403 over HTTP. Full backend suite: 53 passing.
- TDD gotcha: traversal tests must use paths that deterministically resolve to a blocked dir regardless of `tmp_path` depth. `Path("/tmp/../etc")` resolves to `/etc` on any Linux system — using `tmp_workspace / ".." / ".." / "etc"` is fragile because pytest tmp depth varies.

## Wave 2: System Tray + Global Hotkey (Task 10)
- Tauri v2 tray is a feature flag on the core crate: `tauri = { features = ["tray-icon"] }`. NOT a separate plugin. `tauri-plugin-tray` does NOT exist.
- `TrayIconBuilder` lives at `tauri::tray::TrayIconBuilder`. Menu items via `tauri::menu::{Menu, MenuItem}`. `MenuItem::with_id(app, id, label, enabled, accelerator)`.
- `Image::from_path` / `Image::from_bytes` require the `image-png` or `image-ico` feature on the `tauri` crate. Without it, only `Image::new(rgba, w, h)` / `new_owned` are available (raw RGBA). Added `image-png` to Cargo.toml features for the fallback icon path.
- `app.default_window_icon()` returns `Option<Image<'static>>` — the icon configured in tauri.conf.json. Use this as the primary tray icon source; only fall back to `Image::from_path` if None.
- `TrayIconBuilder::menu_on_left_click` is DEPRECATED → use `show_menu_on_left_click`. Set to `false` so left-click triggers `on_tray_icon_event` (toggle window) instead of opening the menu.
- `TrayIconEvent::Click { button: MouseButton::Left, .. }` matches left-clicks. `MouseButton` is at `tauri::tray::MouseButton`.
- Global hotkey: `tauri_plugin_global_shortcut::GlobalShortcutExt` trait provides `app.global_shortcut()` method. Must import the trait. `global.on_shortcut(accelerator_str, handler)` registers. Accelerator string `"Control+Shift+G"` parses via `ShortcutWrapper::try_from(&str)`.
- `ShortcutWrapper` does NOT implement `Debug` — don't use `{:?}` on it in test assertions.
- Minimize-to-tray on close: in `on_window_event` for `WindowEvent::CloseRequested { api, .. }`, call `api.prevent_close()` then `window.hide()`. The `api` field gives mutable access to the close-request guard.
- Capabilities (Tauri v2 ACL): tray + global-shortcut used from Rust do NOT need frontend capability grants. Capabilities are only for JS→Rust command invocations. Build succeeds without any `capabilities/*.json` files.
- Testability: `MenuItem::new` requires a `Manager` (AppHandle), so the menu can't be unit-tested directly. Extracted pure-data `tray_menu_spec() -> &'static [(id, label)]` in lib.rs; `test_tray_menu_items` verifies structure. `test_hotkey_registration` verifies the accelerator string parses via `ShortcutWrapper::try_from`.
- `cargo`/`rustc` ARE available at `~/.cargo/bin/` — add to PATH for all cargo commands.
### Config System
- YAML primary config at ~/.ganesh/config.yaml
- JSON overrides at ~/.ganesh/config.json
- OS Keyring for secrets (service: ganesh)
- Dot notation support for nested keys

## Wave 2: Chat Endpoint (Task 11) — LiteLLM + streaming
- `backend/ganesh_backend/` is a proper Python package (with `routers/`, `services/` subpackages). `main.py` lives at `backend/main.py` (top-level, not inside the package) and imports from `ganesh_backend.routers.*`. The egg-info `top_level.txt` only lists `main` because the package was added after the initial install.
- `services/config.py` already provides `config_service.get_api_key()` (keyring → `OPENAI_API_KEY` env fallback) and `config_service.set_api_key()`. Reuse this — do NOT reimplement keyring access in the LLM service.
- `services/config.py` instantiates `config_service = ConfigService()` at import time, which creates `~/.ganesh/` and writes `config.yaml` if missing. This runs on every import (including tests). Tests that need a clean config dir patch `CONFIG_DIR`/`YAML_CONFIG_PATH`/`JSON_OVERRIDE_PATH` (see `tests/test_config.py`).
- LLM service (`services/llm.py`) wraps `litellm.completion()`. API key is cached via `@lru_cache(maxsize=1)` on `get_api_key()` to avoid hitting the keyring backend on every request. `reset_api_key_cache()` clears it (call after the user updates the key via config UI).
- LiteLLM `completion()` signature: `model, messages, stream=False, api_key=None`. Returns a `ModelResponse` (non-stream) with `.choices[0].message.content` and `.model`, or a `CustomStreamWrapper` (stream) whose chunks have `.choices[0].delta.content` (may be `None` for the final chunk).
- Chat router (`routers/chat.py`): `POST /chat` accepts `{messages, model?, stream?}`. Non-stream returns `ChatResponse(model, content)` JSON. Stream returns `StreamingResponse` with `media_type="text/event-stream"`; chunks formatted as `data: {"content": "..."}\n\n`, terminated with `event: done\ndata: {"done": true}\n\n`. Errors during streaming are emitted as `event: error\ndata: {"error": "..."}\n\n` (can't use HTTPException after headers sent).
- Error mapping: `MissingAPIKeyError` → 401, `LLMError` (wraps all litellm exceptions) → 400, malformed response → 502.
- `main.py` includes the chat router via `app.include_router(chat_router.router, prefix="/api")` → endpoint is `/api/chat`.
- Tests mock `litellm.completion` (not the service wrapper) and `get_api_key` separately, so the keyring path is never exercised in chat tests. Use `SimpleNamespace` to fake LiteLLM response objects.
- Pre-existing `tests/test_search.py` references a not-yet-created `ganesh_backend.routers.search` module (parallel task) — causes a collection error in the full suite. Run with `--ignore=tests/test_search.py` until that task lands.
- Live verification: sidecar with no API key returns 401 (non-stream) and `event: error` SSE (stream) — both correct error paths. Happy-path with a real key can't be verified without OpenAI credentials; the mocked tests cover it.

## Wave 3: Memory Layer (Task 11) — mem0 OSS + LanceDB
- `backend/ganesh_backend/` is now a proper Python package (was flat `main.py` only). Structure: `embeddings.py`, `vector_store.py`, `services/memory.py`, `routers/memory.py`.
- **mem0 OSS integration**: mem0 v2.0.11 does NOT have a built-in LanceDB vector store provider. Built a custom `LanceDbVectorStore` implementing mem0's `VectorStoreBase` interface. The MemoryService uses this adapter directly (not mem0's `Memory` class) because mem0's `Memory.__init__` always creates an LLM via `LlmFactory.create()` — even with `infer=False`, the constructor requires an LLM provider. No mock LLM exists in mem0. Using `Memory` directly would violate "no external services in tests".
- **Embedder strategy**: `EmbedderProtocol` (typing.Protocol) for pluggability. `SentenceTransformerEmbedder` (lazy-imports torch/sentence-transformers, default `all-MiniLM-L6-v2`, 384-dim) for production. `HashEmbedder` (SHA-256-based, deterministic, L2-normalised, no downloads) for tests. `create_default_embedder()` falls back to HashEmbedder if sentence-transformers isn't installed.
- **LanceDB in-memory gotcha**: `lancedb.connect(":memory:")` is SHARED across all connections in the same process. Tests must use unique collection names per fixture (`f"test_memories_{uuid.hex[:8]}"`) to avoid cross-test contamination. The `list_tables()` API returns a `ListTablesResponse` object (not a plain list) — use `.tables` attribute. `table_names()` is deprecated but returns a plain list.
- **Router design**: `get_memory_service()` is a singleton (module-level `_service`). Uses persistent LanceDB at `$GANESH_DATA_DIR/lancedb` (default `~/.ganesh/data/lancedb`). Each request was creating a new service with `:memory:` which caused dimension mismatch errors when the shared in-memory table had a different schema.
- **pyproject.toml**: `lancedb` and `mem0ai` added to main deps. `sentence-transformers` in `[project.optional-dependencies] prod` (heavy, only for production embeddings).
- **NATIVE_DEPS**: Added `lancedb` and `mem0` to the registry in `main.py` for `--check-imports` verification.
- Tests: 4 memory tests (store, retrieve, update, delete) + 6 health + 2 native_deps = 12 passing. Pre-existing `test_files.py` failures are from a different task (file browser, not memory).
