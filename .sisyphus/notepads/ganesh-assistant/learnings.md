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

## Wave 3: STT Integration (Task — voice/stt)
- `services/stt.py`: local engine = faster-whisper (CTranslate2, CPU, int8), cloud fallback = Deepgram nova-2. Both return `TranscriptionResult(text, confidence, engine)`.
- **Lazy import**: `faster_whisper` is imported INSIDE `_load_local_model()`, NOT at module top. This lets `is_local_available()` return False gracefully when the package is missing, and lets tests mock `_load_local_model` without the package installed. Same pattern should be used for any heavy native dep.
- **Model cache**: module-level `_model_cache` (Any, None=not loaded). `reset_model_cache()` clears it (for tests + runtime model-name changes). `is_model_loaded()` reports residency.
- **Confidence math**: faster-whisper segments expose `avg_logprob` (log-prob, roughly [-inf, 0]). Convert to [0,1] confidence via `math.exp(avg_lp)` clamped. exp(-0.3)≈0.74 for a good transcription. Deepgram returns `confidence` directly (already [0,1]).
- **Deepgram key**: `get_deepgram_key()` uses `@lru_cache(maxsize=1)`, resolves from `config_service.get_setting("voice.deepgram_api_key")` → `DEEPGRAM_API_KEY` env. `reset_deepgram_key_cache()` clears it.
- **Async vs sync**: `transcribe_async()` is the FastAPI-friendly path (uses `transcribe_cloud_async` with `await client.post`). The sync `transcribe()` / `transcribe_cloud()` use `run_until_complete` — avoid inside an event loop. Router uses the async variant.
- **Test injection for cloud**: patch `ganesh_backend.services.stt.httpx.AsyncClient` with `side_effect=fake_async_client` that injects a `MockTransport`. Can't pass a client through the router → constructor patch is the cleanest seam.
- **Router**: `POST /api/voice/transcribe` (multipart `file` + form `language`), `GET /api/voice/stt-status` (returns `local_available`, `model_loaded`, `cloud_available`). File is `Optional[UploadFile] = File(default=None)` so missing file → 400 (not FastAPI's 422). 25 MiB upload cap → 413.
- **Temp file spool**: UploadFile bytes → `NamedTemporaryFile(suffix=ext)` → pass path to both engines (faster-whisper needs a path for ffmpeg demux; Deepgram reads raw bytes but path-based keeps the interface uniform). Cleanup via `os.unlink` in `finally`.
- **NATIVE_DEPS**: Added `faster_whisper` to `main.NATIVE_DEPS` tuple. `--check-imports` now verifies it. Added to `docs/NATIVE_DEPS.md` main registry table + `pyinstaller.spec` (`collect_all("faster_whisper")` + `collect_dynamic_libs` for ctranslate2, onnxruntime, av).
- **Concurrent task collision**: A parallel TTS task added `piper` to `NATIVE_DEPS` and a `models` router while I was editing `main.py`. My `faster_whisper` edit was lost on first attempt (oldString matched a stale version). Re-applied after reading the current file state. LESSON: always re-read the file before re-editing when working in a shared tree.
- Tests: 4 in `tests/test_stt.py` (transcribe_mock, stt_status, transcribe_no_audio, cloud_fallback). Full suite: 66 passing.

## Wave 3: TTS Integration (Task 16) — Piper + ElevenLabs fallback
- **Task 15 (STT) had already created `routers/voice.py`** with STT endpoints (`/transcribe`, `/stt-status`) under the `/api/voice` prefix. TTS endpoints were APPENDED to the same router file (not a new router) — `POST /api/voice/synthesize`, `GET /api/voice/tts-status`, `GET /api/voice/voices`. The shared prefix avoids route conflicts and keeps all voice I/O in one router.
- **`main.py` already included `voice_router.router`** (Task 15 wired it). No main.py router registration needed — only added `piper` to the `NATIVE_DEPS` tuple.
- **Piper lazy import**: `piper` is imported inside `_load_piper_voice()` / `_piper_importable()` so the TTS service module loads even when `piper-tts` isn't installed. This is critical for CI/frozen-binary smoke tests. The service's `_local_available()` checks both a configured voice path AND piper importability.
- **Voice model caching**: `_voice_cache: dict[str, Any]` on the TTSService instance, keyed by model path. `_load_piper_voice` returns cached voice on subsequent calls — avoids re-loading the ONNX model per request.
- **Piper API (v1.4.2)**: `piper.PiperVoice.load(model_path)` → `PiperVoice`. `voice.synthesize(text)` yields `AudioChunk` objects with `.audio_int16_array` (numpy int16 array) and `.sample_rate`. `voice.config.sample_rate` gives the sample rate. Assemble chunks into a WAV container via the stdlib `wave` module.
- **ElevenLabs fallback**: `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}` with `xi-api-key` header, JSON body `{"text", "model_id"}`, `Accept: audio/mpeg`. API key resolved from keyring (`ganesh` service, `elevenlabs_api_key` key) → `ELEVENLABS_API_KEY` env. Constructor-injectable `elevenlabs_api_key` override for tests.
- **`piper-tts` IS installable** in this env (pip install piper-tts pulls onnxruntime + pathvalidate). Installed it so `--check-imports` passes with `piper` in `NATIVE_DEPS`.
- **Test mocking for context managers**: `httpx.Client` is used as `with httpx.Client(...) as client:`. To mock, use `MagicMock` with `mock_client.__enter__.return_value = mock_client` and `mock_client.__exit__.return_value = False` — `SimpleNamespace` does NOT support the context manager protocol because dunder methods are looked up on the type, not the instance.
- **Endpoint error codes**: empty/whitespace text → 400 (handled explicitly in router before calling service, AND service raises `ValueError` → router catches → 400). Both backends fail → `TTSError` → 502.
- **pyinstaller.spec**: Uncommented the piper block: `collect_all("piper")` + `collect_dynamic_libs("onnxruntime")`. Task 15 had already activated the faster-whisper block and removed the lancedb block.
- **NATIVE_DEPS.md**: Added piper-tts row to the main registry table; updated the "graduated" note to list piper-tts alongside faster-whisper and lancedb.
- Tests: 4 TTS tests (synthesize_mock, tts_status, synthesize_no_text, cloud_fallback). Full backend suite: 70 passing.

## Wave 3: Accessibility (text-only mode + settings)
- Created `AccessibilityContext.tsx` with `textOnlyMode`, `fontSize` (small/medium/large), `highContrast`, `reducedMotion` — all persisted to localStorage key `ganesh.a11y`.
- State is reflected onto `documentElement` as data attributes: `data-text-only`, `data-font-size`, `data-contrast`, `data-motion`. CSS attribute selectors in `theme.css` apply the overrides (font-size scales root font-size, high-contrast overrides semantic vars, reduced-motion nukes animation/transition durations).
- `ChatContainer.tsx` shows a `text-only-banner` and hides `voice-controls` bar when text-only is on. `ChatInput.tsx` hides the mic button (`data-testid="mic-button"`) and shows a `send-confirmation` toast for 1.2s after send.
- `AccessibilitySettings.tsx` renders toggles (role="switch" + aria-checked), font-size button group (aria-pressed), and a reset button.
- `App.tsx` wraps with `AccessibilityProvider` inside `ThemeProvider`, adds an a11y toggle button in the header alongside the theme toggle.
- **Cross-test DOM pollution**: vitest `singleThread: true` shares jsdom DOM across test files. testing-library auto-cleanup does NOT fire reliably — must explicitly `import { cleanup } from '@testing-library/react'` and call it in `afterEach` (or `beforeEach`). Without this, rendered components leak across test files causing "Found multiple elements" errors.
- **Parallel task conflicts**: ChatContainer.tsx and App.tsx were modified by a concurrent task (theme switcher + document thumbnails). Had to merge: re-add `useAccessibility` import (lost in overwrite), fix duplicate `import { useState }` lines, pass required `documents`/`onOpenDocument` props to ChatContainer, fix orphaned code in ChatMessage.tsx (lines 85-110 were duplicate leftover from a botched edit), fix `message: ChatMessage` → `message: ChatMessageType` type bug.
- ChatInput now requires `AccessibilityProvider` — updated `chat.test.tsx` to wrap renders in provider via `renderChatInput()` helper.
- Pre-existing failures (not mine): `waveform-render.test.ts` (3 tests fail in isolation — WaveformVisualizer.render static method issue), `ModelDownload.test.tsx` (was failing before my changes, now passes after cleanup fixes).

## Wave 3: Model Download (Task — first-run model download UX)
- `services/model_manager.py` is HTTP-client-pluggable: `download_model(name, client=...)` accepts an `httpx.AsyncClient` so tests inject `httpx.MockTransport`-backed clients (same pattern as `services/search.py`). No real network in tests.
- Resume support: download writes to `<name>.bin.part`; on next run the existing `.part` size is sent as `Range: bytes=<offset>-`. Server responds 206 with the tail; we append. If server ignores Range (returns 200), we restart from scratch. On checksum success, `.part` → `.bin` rename.
- SHA-256 verification: `download_model` raises `ValueError("checksum mismatch...")` and deletes the `.part` file on mismatch. Progress is marked `status="failed"` with the error message.
- `DownloadProgress` dataclass uses an internal `threading.Lock` (field with `default_factory`, `repr=False`) so `update()`/`snapshot()` are thread-safe for the SSE stream reading while the download task writes.
- Pause/resume: `threading.Event` per model name. The download loop checks `pause_event.is_set()` between chunks and sleeps (status="paused") until cleared. `cancel_event` short-circuits the loop.
- Router `routers/models.py`: 5 endpoints under `/api/models`. `GET /progress` is an SSE stream (`StreamingResponse`, `media_type="text/event-stream"`) that emits `data: {"models": {...}}\n\n` on snapshot change and `event: done` when all complete. Idle timeout (600 ticks × 0.5s = 5min) prevents infinite streams.
- `main.py` mounts via `app.include_router(models_router.router)` — the router has its own `prefix="/api/models"`.
- Frontend `ModelDownload.tsx`: modal shown when `GET /api/models/status` returns `all_present=false` OR on fetch error. Uses `EventSource` for `/api/models/progress` SSE (port read from `localStorage['ganesh_sidecar_port']`). Per-model rows show progress bar, %, speed, ETA, status badge, and contextual Download/Pause/Resume/Retry buttons.
- **Test isolation gotcha**: `@testing-library/react` auto-cleanup doesn't always fire in vitest's threaded pool. Add explicit `cleanup()` in `afterEach` when a component renders into `document.body` and multiple tests in the same file use `screen.getByTestId` — otherwise DOM from previous tests leaks and `getAllByTestId` returns stale elements.
- **useCallback hoisting**: a `useEffect` cleanup referencing a `useCallback` defined LATER in the same component body throws `ReferenceError` at mount (TDZ). Define `stopProgressStream` BEFORE the `useEffect` that uses it.
- mypy strict: `dict[str, asyncio.Task]` needs `dict[str, "asyncio.Task[object]"]` (Task is generic). `httpx.AsyncClient.close()` doesn't exist — use `aclose()`.
- Pre-existing failures (not from this task): `test_check_imports`, `test_native_deps` (parallel voice task added `piper` to NATIVE_DEPS but piper isn't installed); `test_stt.py::test_cloud_fallback` (voice task). Frontend: `ThemeContext.test.tsx` (6) + `waveform-render.test.ts` (1) fail in full-suite but pass in isolation — pre-existing test-isolation issues from parallel visualizer/accessibility tasks.
- Verification: backend `pytest tests/test_models.py -v` → 5 passed. Frontend `vitest run src/__tests__/ModelDownload.test.tsx` → 10 passed. mypy clean, ruff clean.

## Wave 3: Voice Activation (Task 17) — push-to-talk / wake-word / VAD + barge-in
- `VoiceActivationService` is a thread-safe (RLock) finite-state machine: IDLE → LISTENING → PROCESSING → SPEAKING → (barge-in) → LISTENING. States live in `VoiceState` enum; modes in `ActivationMode` enum.
- `sherpa-onnx` is imported lazily inside `_is_wake_word` / `_is_voice_activity`; tests inject fakes via the `wake_word_detector` / `vad_detector` ctor params (duck-typed Protocols). No model downloads at import time.
- Barge-in cancels both TTS and LLM via injected `tts_canceller` / `llm_canceller` callables (kept exception-swallowing so a failing canceller never blocks the state transition).
- Singleton pattern mirrors stt/tts: `get_voice_activation_service()` / `reset_voice_activation_service()` / `set_voice_activation_service()` (the last lets tests wire a mocked instance into the router).
- Router additions on `/api/voice`: `start-listening`, `stop-listening`, `audio-chunk`, `barge-in`, `state`, `set-mode`, `reset`. Illegal transitions return 409.
- Frontend `VoiceActivation.tsx` uses `navigator.mediaDevices.getUserMedia({ audio: true })`, `MediaRecorder` for push-to-talk, `AudioContext` + `ScriptProcessor` for VAD/wake-word streaming. jsdom has neither — tests must polyfill `MediaRecorder` and `AudioContext` with fake classes and stub `navigator.mediaDevices`.
- Tauri CSP updated: added `media-src 'self'` to allow microphone capture in the webview.
- Pre-existing tsc errors (21 lines) and 4 vitest failures in `holo-face-visualizer.test.ts` / `freq-bars-visualizer.test.ts` / `particle-visualizer.test.ts` are from Task 18/19 (visualizer + holo-face) and are OUT OF SCOPE for Task 17 — do not touch.

## Wave 2: Additional Visualizers (Task 19) — freq bars, particles, holo-face
- Three visualizers added: `FreqBarsVisualizer` (Canvas 2D bar graph), `ParticleVisualizer` (Canvas 2D particle system), `HoloFaceVisualizer` (Three.js wireframe icosahedron with vertex displacement).
- `VisualizerCanvas.tsx` updated to detect WebGL plugins by name (`'Holo Face'`) and use `webgl2` context instead of `2d`.
- All visualizers registered in `VoiceVisualizer.tsx` via `register()` calls at module evaluation time.
- `index.ts` exports all four visualizers.
- **Module-level state pattern**: `ParticleVisualizer` and `HoloFaceVisualizer` use module-level `const` state objects instead of properties on the `VisualizerPlugin` object literal, because the interface doesn't allow extra properties. This avoids TS2353 errors.
- **Three.js mock gotcha**: When mocking Three.js for tests, every object returned by constructors must have ALL methods that the real code calls — including `geometry.dispose()` on `Points`. Missing this causes `TypeError: X.dispose is not a function` at runtime.
- **Registry clear() gotcha**: `VoiceVisualizer` registers plugins at module load time (top-level `register()` calls). Calling `clear()` in test `beforeEach` wipes the registry AFTER modules are loaded, so plugins are gone. Solution: don't `clear()` in tests that render `VoiceVisualizer`, or re-register before each test.
- `three` and `@types/three` added to package.json.
- All 124 tests pass (17 test files), tsc --noEmit clean.

## Wave 2: Additional Visualizers (Task 19) — freq bars, particles, holo-face
- Three visualizers added: `FreqBarsVisualizer` (Canvas 2D bar graph), `ParticleVisualizer` (Canvas 2D particle system), `HoloFaceVisualizer` (Three.js wireframe icosahedron with vertex displacement).
- `VisualizerCanvas.tsx` updated to detect WebGL plugins by name (`'Holo Face'`) and use `webgl2` context instead of `2d`.
- All visualizers registered in `VoiceVisualizer.tsx` via `register()` calls at module evaluation time.
- `index.ts` exports all four visualizers.
- **Module-level state pattern**: `ParticleVisualizer` and `HoloFaceVisualizer` use module-level `const` state objects instead of properties on the `VisualizerPlugin` object literal, because the interface doesn't allow extra properties. This avoids TS2353 errors.
- **Three.js mock gotcha**: When mocking Three.js for tests, every object returned by constructors must have ALL methods that the real code calls — including `geometry.dispose()` on `Points`. Missing this causes `TypeError: X.dispose is not a function` at runtime.
- **Registry clear() gotcha**: `VoiceVisualizer` registers plugins at module load time (top-level `register()` calls). Calling `clear()` in test `beforeEach` wipes the registry AFTER modules are loaded, so plugins are gone. Solution: don't `clear()` in tests that render `VoiceVisualizer`, or re-register before each test.
- `three` and `@types/three` added to package.json.
- All 124 tests pass (17 test files), tsc --noEmit clean.

## Wave 3: Async Task Manager (Task 24) — SQLite status store
- `TaskManager` (`ganesh_backend/services/task_manager.py`) uses SQLite for persistence + `asyncio.Task` for in-flight work. Schema: `tasks(id, goal, status, current_action, result_json, started_at, completed_at, task_type)`.
- Task lifecycle: PENDING → RUNNING → COMPLETED/FAILED/CANCELLED/INTERRUPTED. Terminal states set `completed_at`.
- DB path defaults to `$GANESH_DATA_DIR/ganesh.db` or `~/.ganesh/ganesh.db` (mirrors memory router's `_data_dir` pattern but at the `~/.ganesh` root, not `~/.ganesh/data`).
- Task function registry: `register_task_type(task_type, fn)` where `fn` is `async (task_id, input, ctx) -> Any`. `TaskContext.report_progress(action, progress)` updates DB + notifies SSE subscribers.
- Orphaned recovery: `__init__` calls `_recover_orphaned()` which `UPDATE tasks SET status='interrupted', completed_at=now WHERE status IN ('running','pending')`. This handles sidecar crashes.
- SSE streaming: `get_task_stream(task_id)` is an async generator backed by per-task `asyncio.Queue` subscriber lists. `_publish` broadcasts to all queues. `_drop_task` pushes a `{"_done": True}` sentinel so streams terminate when the task finishes.
- Router (`ganesh_backend/routers/tasks.py`): `POST /api/tasks`, `GET /api/tasks`, `GET /api/tasks/{id}`, `POST /api/tasks/{id}/cancel`, `GET /api/tasks/{id}/stream`. SSE stream does a final DB read after the in-memory stream ends so clients always see the settled terminal state.
- Singleton pattern: `get_task_manager()` / `reset_task_manager()` / `set_task_manager()` mirrors voice_activation/model_manager. Router exposes `reset_router_singleton()` for tests.
- Tests (`tests/test_task_manager.py`): 5 tests, all `@pytest.mark.asyncio` (strict mode). Use `tmp_path` fixture for file-based SQLite (NOT `:memory:` — each connection is isolated in SQLite's memory mode, so persistence test would fail). Mock task functions use `asyncio.sleep(0.05)` — no real long-running work.
- `_abort_in_memory(task_id)` is a test-only method that cancels the asyncio.Task WITHOUT updating the DB row, simulating a crash that leaves the row stuck at "running" for orphaned-recovery verification.
- pytest-asyncio 1.4.0 is in strict mode by default (no `asyncio_mode` config in pyproject.toml) — must use `@pytest.mark.asyncio` on every async test.
- ruff E402: test files that `sys.path.insert` before imports need `# noqa: E402` on the import line (matches test_models.py / test_voice_activation.py pattern).
- mypy: pre-existing errors in main.py (sentence_transformers, faster_whisper, yaml stubs, numpy py.typed) are unrelated to new code — new files (`task_manager.py`, `tasks.py`) are mypy-clean.
- Full suite: 79 tests passing (74 baseline + 5 new).

## Task 25: Sub-Agent Orchestration
- SubAgentRunner registers a single TaskManager task type ("sub_agent"); the user-facing task_type (research/coding/...) is carried inside the task input payload so the orchestrator can distinguish sub-agent kinds without polluting the TaskManager registry.
- Orchestrator status/result queries go straight to TaskManager.get_task (non-blocking SQLite read) — safe to call from the chat flow without awaiting the asyncio task.
- build_result_context_message produces a system-role message injecting the completed sub-agent's output into the main agent's LLM context (the "result piped to main" requirement).
- Agents router adds POST /api/agents/spawn, GET /api/agents, GET /api/agents/{id}/status, GET /api/agents/{id}/result, POST /api/agents/{id}/cancel. The cancel endpoint is required by the TaskPanel's cancel button even though the spec only listed 4 endpoints.
- TaskPanel auto-refreshes via setInterval (default 2s); fake timers + async hooks = pain (known), so the auto-refresh test uses real timers with a 200ms interval + waitFor.
- When a concurrent task (Task 26 plugins) is modifying main.py in the same working tree, `git checkout backend/main.py` then re-applying only my edit produced a clean commit. Restore the other task's changes to the working tree afterwards so it isn't disrupted.

## Wave 3: Dynamic Plugin System (Task — importlib + manifest)
- `PluginRegistry` (`services/plugin_registry.py`): thread-safe (RLock) store of `PluginEntry` + `ToolEntry` dataclasses. Tools keyed by qualified name `plugin.tool` for O(1) lookup; bare names matched only when unambiguous. Singleton pattern mirrors task_manager/voice_activation: `get_registry()` / `reset_registry()` / `set_registry()`.
- `PluginLoader` (`services/plugin_loader.py`): discovers subdirs of `~/.ganesh/plugins/` (or `$GANESH_DATA_DIR/plugins/`) containing both `manifest.json` + `plugin.py`. Uses `importlib.util.spec_from_file_location` + `module_from_spec` + `exec_module` for dynamic loading. Modules registered in `sys.modules` under `ganesh_plugin_<name>` so they're importable by other code if needed.
- Manifest schema: `{name, version, description, entry_point, tools: [{name, description, parameters}]}`. `entry_point` is a callable in `plugin.py` with signature `register(registry: PluginRegistry, manifest: dict) -> None` — the plugin is responsible for calling `registry.register_tool(...)` for each declared tool, wiring the manifest's tool schema to the implementing callable. This keeps the loader generic (no introspection of tool callables) and the plugin in control of its own registration.
- Hot-reload (`reload_plugins()`): drops all `ganesh_plugin_*` entries from `sys.modules`, clears the registry, and re-imports. Source edits take effect without a sidecar restart. `load_plugin()` also calls `unregister_plugin(name)` before registering, so re-loading a single plugin is safe.
- Router (`routers/plugins.py`): 4 endpoints under `/api/plugins`: `GET ""` (list plugins), `GET /tools` (list tools), `POST /{plugin}/{tool}/invoke` (invoke with `{"parameters": {...}}` body), `POST /reload` (hot-reload). `reset_router_singletons()` + `set_router_singletons(loader, registry)` for test injection.
- `main.py` lifespan loads all plugins on startup via `get_loader().load_all()`. `load_all()` catches `PluginLoadError` per-plugin (logs a warning, skips) so one bad plugin doesn't break the sidecar.
- Example plugin at `backend/plugins/example/`: `take_note(text)` saves to `~/.ganesh/notes/note-<timestamp>.txt`. Tests write their own temp plugin (not the example) to avoid coupling to the shipped example's source.
- Tests: 5 in `tests/test_plugins.py` (discovery, load, invoke, hot-reload, router smoke). All use `tmp_path` + `monkeypatch.setenv("GANESH_DATA_DIR", ...)` so the real `~/.ganesh/` is never touched. The hot-reload test mutates the plugin source on disk and verifies the reloaded function's behavior changed.
- **Parallel task collision (Task 25 sub-agents)**: A concurrent task added an `agents` router to `main.py` and my edits to `main.py` (import + lifespan + include_router) were overwritten THREE times during this session. LESSON REINFORCED: always re-read `main.py` before re-editing when working in a shared tree, and verify with `grep` after each edit. The `app.include_router(plugins_router.router)` line was silently dropped twice.
- No new native deps — plugin system uses only stdlib (`importlib`, `json`, `pathlib`, `threading`). `docs/NATIVE_DEPS.md` unchanged.
- Full backend suite: 87 tests passing (82 baseline + 5 new). ruff clean, mypy clean on new files (pre-existing numpy stub error is unrelated).

## Wave 3: Dynamic Plugin System (Task — importlib + manifest)
- **Plugin contract**: each plugin is a subdirectory under `~/.ganesh/plugins/` (or `$GANESH_DATA_DIR/plugins`) containing `manifest.json` + `plugin.py`. The manifest declares `{name, version, description, entry_point, tools: [{name, description, parameters}]}`. `entry_point` is the NAME of a callable inside `plugin.py` with signature `register(registry, manifest) -> None` — the plugin self-registers its tools by calling `registry.register_tool(plugin_name, tool_name, fn, schema)`. This is more flexible than matching tool names to module attributes (lets plugins wire closures/async wrappers).
- **Registry design**: `PluginRegistry` stores plugins as `PluginEntry` dataclasses and tools as `ToolEntry` dataclasses keyed by qualified name `plugin.tool`. `get_tool()` supports both qualified (`plugin.tool`) and bare (`tool`) names (bare only when unambiguous). Thread-safe via RLock.
- **Loader**: `PluginLoader` uses `importlib.util.spec_from_file_location` with a synthetic module name `ganesh_plugin_<name>` to avoid collisions. Hot-reload drops modules from `sys.modules` and re-imports fresh so source edits take effect without a process restart. `reload_plugins()` clears the registry first so a failed reload doesn't leave stale tools.
- **Router**: `/api/plugins` (list), `/api/plugins/tools` (list), `/api/plugins/{plugin}/{tool}/invoke` (POST with `{"parameters": {...}}`), `/api/plugins/reload` (POST). Invoke is sync-only (`entry.fn(**params)`) — async tool support would need `inspect.iscoroutinefunction` + await.
- **Pydantic field shadowing**: `schema` is a reserved-ish attribute on `BaseModel` — using `schema` as a field name triggers a `UserWarning`. Renamed to `tool_schema` in the `ToolSummary` response model.
- **Startup side effect**: `create_app()` calls `get_loader().load_all()` so `/api/plugins` is populated on boot. Wrapped in `try/except` so a bad plugin never blocks sidecar startup.
- **Concurrent task collision (again)**: Task 25 (sub-agents) added `agents_router` to `main.py` WHILE I was editing it. My first `plugins_router` include was lost. Re-applied after re-reading the current file state. LESSON REINFORCED: always re-read shared files before re-editing in a concurrent tree.
- **No new native deps**: plugin system uses only stdlib (`importlib`, `json`, `pathlib`). No `NATIVE_DEPS.md` update needed.
- Tests: 5 in `tests/test_plugins.py` (discovery, load, invoke, hot-reload, router smoke). Full suite: 87 passing (82 baseline + 5 new). ruff + mypy clean on new files.

## Wave 3: Multi-Provider LLM (Task — Anthropic, Google, OpenRouter via LiteLLM)
- LiteLLM 1.91.0 supports openai/anthropic/google/openrouter via direct HTTP calls — NO need to install `anthropic` or `google-generativeai` SDK packages. LiteLLM makes the HTTP calls itself using `httpx`.
- LiteLLM model-prefix conventions (critical, non-obvious):
  - openai: plain model name (`gpt-4o-mini`)
  - anthropic: plain model name (`claude-3-5-sonnet-20240620`) — litellm auto-detects the `claude-` prefix
  - google: REQUIRES `gemini/` prefix (`gemini/gemini-1.5-flash`) — litellm won't route without it
  - openrouter: REQUIRES `openrouter/` prefix (`openrouter/openai/gpt-4o-mini`)
  - `_litellm_model_name(provider, model)` applies the prefix when the caller hasn't already supplied it (idempotent — safe to pass a pre-prefixed name).
- API key storage: keyring service `ganesh`, key `ganesh_api_key_{provider}` (e.g. `ganesh_api_key_anthropic`). Env fallback vars: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`.
- `get_api_key(provider)` uses `@lru_cache(maxsize=None)` (per-provider cache) — `reset_api_key_cache()` clears ALL cached keys (call after any key update via config UI).
- `ConfigService` extended with `get_provider_key(provider)` (keyring only), `get_provider_key_env(provider)` (env only), `set_provider_key(provider, key)`, `is_provider_configured(provider)`. The original `get_api_key()`/`set_api_key()` (openai-specific) are kept for backward compat with existing tests.
- Chat router `ChatRequest` now has `provider: str = "openai"` (defaults to openai for backward compat — existing clients sending only `{messages, model}` still work). `ChatResponse` now includes `provider` field. Unknown provider → 400 (validated in router BEFORE calling the service so the error message is consistent).
- Config router new endpoints: `GET /api/config/providers` (list with `configured` bool), `POST /api/config/providers/{provider}/key` (store + reset llm cache), `GET /api/config/providers/{provider}/models` (list models), `POST /api/config/providers/{provider}/test` (test connection). The key-storage endpoint calls `llm_service.reset_api_key_cache()` so the next chat request picks up the new key without a sidecar restart.
- `test_connection(provider)` makes a `max_tokens=1` completion call — returns `True`/`False` (never raises for runtime errors; only raises `UnsupportedProviderError` for programmer error). `MissingAPIKeyError` is caught internally → returns `False`.
- Tool calling: LiteLLM normalizes OpenAI-format tool definitions across providers — pass `tools=[{"type":"function","function":{...}}]` and litellm handles the per-provider format translation. No adapter shim needed for the tool INPUT; the tool_calls in the RESPONSE come back in normalized OpenAI format (`message.tool_calls[i].function.name/arguments`). This is why the spec said "add adapter if needed" — it wasn't needed.
- Frontend `ProviderSettings.tsx`: provider dropdown (loads from `/api/config/providers`), model dropdown (loads from `/api/config/providers/{provider}/models` on provider change), API key input with show/hide toggle, Test Connection button (saves key first, then calls test endpoint), Save button. Test result shown as green/red banner. Buttons disabled when no API key entered.
- Frontend test pattern: mock `sidecarFetch` with chained `mockResolvedValueOnce` for the sequential API calls (providers list → models list → save key → test). Use `waitFor` on the last expected DOM state.
- No new native deps — litellm was already in NATIVE_DEPS. No NATIVE_DEPS.md update needed.
- Tests: 14 in `tests/test_llm_providers.py` (5 required + 9 additional for router/config coverage). Full backend suite: 108 passing (the 1 failure in `test_conversations.py` is from a parallel untracked task, not mine). Frontend: 137 passing (7 new in `ProviderSettings.test.tsx`).

## Wave 3: Multi-Provider LLM Support (Task 28)
- LiteLLM model-prefix conventions: openai=plain name, anthropic=plain name (litellm auto-detects `claude-`), google=`gemini/<model>`, openrouter=`openrouter/<vendor>/<model>`.
- Provider API keys stored in keyring under service="ganesh", username=`ganesh_api_key_{provider}`. Legacy `openai_api_key` username kept for backward compat.
- `get_api_key(provider)` is lru_cached per-provider; `reset_api_key_cache()` clears all caches (call after key updates via config UI).
- LiteLLM normalizes tool-call format across providers — pass tools in OpenAI format, litellm translates to Anthropic's tool_use blocks internally. No manual adapter needed.
- `test_connection(provider)` makes a minimal `max_tokens=1` call; returns bool (False on any exception including MissingAPIKeyError).
- Chat router `ChatRequest` model has `provider: str = DEFAULT_PROVIDER` (defaults to "openai") for backward compat.
- Config router endpoints: GET /api/config/providers, POST /api/config/providers/{provider}/key, GET /api/config/providers/{provider}/models, POST /api/config/providers/{provider}/test.
- No new native deps — litellm (already registered) handles all 4 providers.
- Pre-existing broken `test_conversations.py` is from an unrelated incomplete feature; exclude with `--ignore=tests/test_conversations.py` when running full suite.

## Wave 3: Conversation History (Task — persistence + search + export + delete)
- `ConversationStore` (`services/conversations.py`): SQLite for conversations + messages, LanceDB for message embeddings (semantic search). Schema: `conversations(id, title, profile_id, created_at, updated_at)`, `messages(id, conversation_id, role, content, created_at)` with FK CASCADE.
- SQLite path defaults to `$GANESH_DATA_DIR/conversations.db` (or `~/.ganesh/data/conversations.db`). LanceDB URI defaults to `:memory:` in the service constructor but the router overrides to `$GANESH_DATA_DIR/lancedb` for production.
- `check_same_thread=False` on sqlite3.connect is required — FastAPI's threadpool calls the store from worker threads. SQLite serialises writes internally so this is safe.
- Auto-title: first 50 chars of first user message when title is still "New Conversation". Updated in the same transaction as the message insert.
- Embedding is best-effort: wrapped in try/except so a LanceDB failure never breaks message persistence. This is critical for offline/degraded operation.
- **HashEmbedder limitation**: it's deterministic but NOT truly semantic — it hashes 8-byte text windows at 4-byte strides. Short texts get artificially high cosine similarity because most dimensions are a constant baseline (when offset > text length, the chunk is just the dimension index). Tests must assert membership (the relevant conversation appears in results) rather than strict rank-1 ordering. The memory layer's tests work because all stored memories are similar length, so the baseline effect is uniform.
- Router (`routers/conversations.py`): 7 endpoints under `/api/conversations`. `GET /search?q=` uses `alias="q"` so the query param is `q` (short) while the Python param is `q`. Export is `POST /{id}/export` with body `{"format": "json|markdown"}` — returns `{format, content}` so the frontend can trigger a Blob download.
- Singleton pattern: `get_conversation_service()` / `reset_conversation_service()` / `set_conversation_service()` for test injection (same as memory/task_manager/voice_activation).
- Frontend `ConversationHistory.tsx`: sidebar panel with search (debounced 300ms), list, export dropdown (JSON/Markdown), delete with confirmation modal. Uses `sidecarFetch` mock pattern from TaskPanel. 7 tests cover render, empty state, select, search, export, delete, error.
- Chat integration: `useChat` hook now creates a conversation on first message (`ensureConversation`), persists each message (`persistMessage`), and exposes `loadConversation(conv)` to load a past conversation. `conversationId` is in the return. `clearMessages` resets `conversationId` to null so the next message starts a new conversation.
- App.tsx ↔ ChatContainer decoupling: App owns the history sidebar; ChatContainer owns the chat. A `CustomEvent('ganesh:load-conversation')` bridges them — App dispatches on sidebar select, ChatContainer listens and calls `loadConversation`. This avoids lifting useChat to App level (which would require refactoring ChatContainer's entire prop interface).
- **Pre-existing file collision**: `services/conversations.py` and `tests/test_conversations.py` already existed from a previous (incomplete) attempt. The service had a Python syntax error (misindented block in `add_message`). Rewrote the service cleanly; fixed the search test assertion (rank-1 → membership). The test file had 7 tests (5 required + 2 extra: auto-title + list).
- **Duplicate file content**: `useChat.ts` and `App.tsx` had full duplicate content from the previous attempt (two copies of the same functions/state declarations). Truncated `useChat.ts` to 240 lines; rewrote `App.tsx` cleanly. Always check for duplicates when inheriting incomplete work.
- Verification: backend 7/7 pass, full suite 96 pass. Frontend 144/144 pass (20 files), tsc clean.

## Task 11: Conversation History (persistence + search + export + delete)
- LanceDB `:memory:` URI creates a PERSISTENT directory named `:memory:` in the CWD — it is NOT truly in-memory! All tests using `:memory:` share the same directory, causing cross-test contamination. Use a temp directory (e.g. `tmp_path / "lancedb"`) in test fixtures instead.
- HashEmbedder produces deterministic but NOT semantically meaningful vectors (hash-based). Pure vector search ranks arbitrarily. Implemented hybrid search: vector similarity + keyword matching (SQLite LIKE), sorted by (keyword_score, vector_score). This makes search actually work with HashEmbedder.
- Conversation auto-title: first 50 chars of first user message, truncated (no ellipsis). Default title "New Conversation" replaced on first user message.
- useChat persistence: best-effort, fire-and-forget. `ensureConversation` creates conversation on first message, `persistMessage` saves user+assistant messages. All persistence errors caught silently so chat still works when backend is unavailable. This pattern keeps existing chat streaming tests passing (mock returns non-Response object, persistence calls fail silently).
- Cross-component communication for loading conversations: used `window.dispatchEvent(new CustomEvent('ganesh:load-conversation', { detail: conv }))` from App.tsx, ChatContainer listens via `useEffect`. Avoids lifting useChat to App level.
- tsc stale cache can produce false "Cannot redeclare" errors. Clearing tsbuildinfo or re-running resolves it.

## Wave 4: Personality Trait Matrix (Task 30)
- `PersonalityEngine` lives in `backend/ganesh_backend/services/personality.py`. Module-level singleton `engine` is used by the router; tests inject a `FakeConfig` via `PersonalityEngine(config=...)` to avoid touching the real config.yaml.
- Trait bounds are asymmetric: `formality`, `verbosity`, `assertiveness` are bipolar [-1.0, 1.0]; `warmth`, `humor` are unipolar [0.0, 1.0]. This is documented in `TRAIT_BOUNDS` and the spec — do NOT normalize.
- `MUTATION_RATE_CAP = 0.15` caps per-shift delta. The `_analyze_context` heuristic normalizes raw keyword counts to [-cap, +cap] BEFORE applying, then `shift_traits` clamps the result to trait bounds. Two-stage clamping is intentional.
- Shifts are session-scoped: `_current` dict drifts from `_baseline` but `_baseline` (loaded from config) is never written back. `reset_traits()` copies baseline into current. A fresh `PersonalityEngine` instance reads the original baseline.
- Locked traits: `_locked` set loaded from `personality.locked` config list. `shift_traits` skips locked traits. `lock_trait`/`unlock_trait` mutate the in-memory set only (not persisted).
- Context heuristics are deliberately simple deterministic keyword counters (Task 35 owns proactive learning). Each trait has opposing token pairs (casual/formal, warm/cold, etc.).
- Router prefix: `/api/personality`. Endpoints: GET/PUT `/traits`, POST `/shift`, POST `/lock/{trait}`, POST `/unlock/{trait}`, POST `/reset`, GET `/system-prompt`.
- Frontend `PersonalityPanel.tsx`: sliders per trait (range input, step 0.05), lock toggle (🔒/🔓), reset button, shows current vs baseline. Uses `sidecarFetch` like other panels.
- vitest slider value assertion: `toHaveValue('0.1')` (string), NOT `toHaveValue(0.1)` (number) — range inputs stringify.
- Pre-existing frontend test failures in `ProviderSettings.test.tsx` (2) and `documentViewer.test.tsx` (6) are from other in-progress work (local LLM task) — NOT caused by personality changes. Confirmed zero references to personality code in those files.

## Wave 3: Local LLM Support (Task — Ollama/LM Studio via OpenAI-compatible endpoints)
- Local provider routes through LiteLLM with `model="openai/<model>"` + `api_base=<base_url>` — LiteLLM uses the OpenAI provider path against the custom endpoint. No `anthropic`/`google` SDK needed.
- `get_api_key("local")` returns a placeholder `"not-required"` — never raises `MissingAPIKeyError`. The local provider short-circuits in `get_api_key` before the keyring/env lookup.
- `get_available_models("local")` fetches dynamically from `GET {base_url}/models` (OpenAI-compatible `/v1/models` endpoint) via `httpx.get`, returns `[]` on any error. This differs from cloud providers which use a static `PROVIDER_MODELS` registry.
- `test_connection("local")` validates endpoint reachability via `GET {base_url}/models` (not a completion call) — avoids requiring a model to be loaded just to test connectivity.
- Config storage: `llm.local.base_url` and `llm.local.model` via `config_service.set_setting` (YAML dot-notation). New router endpoint `POST /api/config/providers/local/endpoint` stores both.
- `is_provider_configured("local")` checks `llm.local.base_url` presence (not keyring) — local has no key.
- Frontend `ProviderSettings.tsx`: when `selectedProvider === 'local'`, renders base URL + model text inputs instead of model dropdown + API key input. The `canSaveOrTest` flag uses `localBaseUrl.trim()` for local, `apiKey.length` for cloud.
- Pre-existing bug in `main.py:126`: `personality_router.router` should be `personality_router` (the import is `from ... import router as personality_router`). Fixed to unblock all main-importing tests.
- Frontend test gotcha: when rendering ProviderSettings with default provider 'openai', the useEffect fires `loadModels('openai')` which consumes a mock. Local-provider tests must mock the initial models fetch too (`.mockResolvedValueOnce(mockResponse({ models: OPENAI_MODELS }))`) even though they immediately switch to 'local'.
- No new native deps — `httpx` was already a runtime dependency, `litellm` already in NATIVE_DEPS. No NATIVE_DEPS.md update needed.
- Tests: 9 in `tests/test_local_llm.py` (3 required + 6 coverage). Full backend suite: 122 passing. Frontend: 10 in ProviderSettings.test.tsx (3 new local tests). tsc clean.
## Git Master Learnings
- Always check if files are already tracked before assuming they are ignored.
- Use `git add -f` if a file is explicitly ignored but needs to be tracked.
- Fix `.gitignore` patterns to be more standard (e.g., `.sisyphus/*` instead of `.sisyphus/` if you want to unignore subdirectories).
- Conventional Commits style detection is crucial for maintaining repo consistency.

## Wave 3: Personality Persistence (Task — save/load trait state to disk)
- **3-layer state model** required to satisfy all test cases:
  - `_persisted_baseline`: last saved profile (from disk or config). Modified only by `save()`/`load()`.
  - `_baseline`: working profile, modified by `set_trait`. What `save()` writes.
  - `_current`: baseline + session shifts (what LLM sees). Shifts never touch `_baseline`.
- **Key invariant**: `save()` writes `_baseline` (NOT `_current`) so context shifts are never persisted. `reset_traits()` restores both `_baseline` and `_current` to `_persisted_baseline` (discards unsaved `set_trait` changes + shifts).
- **`persist` flag semantics**: `set_trait(trait, value, persist=False)` updates `_baseline` + `_current` but does NOT call `save()`. `persist=True` updates + saves. The router passes `persist=True` by default (auto-save). `POST /save` explicitly calls `save()` to flush the working baseline.
- **2-layer model is insufficient**: if `set_trait` only updates `_current` (not baseline), then `POST /save` can't persist user-set values. If `set_trait` updates baseline AND there's no `_persisted_baseline` layer, then `reset_traits()` can't discard unsaved `set_trait` changes.
- **Parallel task collision (again)**: A concurrent task had modified `personality.py` and `personality_router.py` with a 2-layer model (`save()`/`load()`/`has_persisted_state()`/`get_engine()`/`set_engine()`/`reset_engine()` API). My initial write created duplicate method definitions (Python silently uses the last definition). Had to reconcile by adopting the parallel task's API names while adding the 3rd state layer (`_persisted_baseline`) needed for correct semantics.
- **Test isolation**: `fake_config` fixture now sets `GANESH_DATA_DIR` to `tmp_path` via `monkeypatch.setenv` so tests don't pick up real `~/.ganesh/personality.json`. Tests also pass `persistence_path=tmp_path / "personality.json"` explicitly.
- **Router API test pattern**: use `set_engine(test_engine)` from the service module to inject a test engine — the router uses `get_engine()` not a module-level `default_engine` variable.
- **Shift context matters for test assertions**: formal tokens ("dear regards sincerely") don't affect warmth; use cold tokens ("urgent asap immediately now error broken") to shift warmth down from 0.9.
- Persistence file: `~/.ganesh/personality.json` (or `$GANESH_DATA_DIR/personality.json`), JSON format with `{"traits": {...}, "locked": [...]}`.
- Tests: 10 backend (5 existing + 5 new), 9 frontend. All pass. tsc clean.

## Wave 4: Personality Persistence (Task — save/load trait state to disk)
- **Persistence model**: the engine maintains TWO dicts — `_baseline` (user-set, persisted to `~/.ganesh/personality.json` or `$GANESH_DATA_DIR/personality.json`) and `_current` (baseline + session-scoped context shifts, in-memory only). `save()` writes `_baseline` ONLY — never `_current`. This is the core invariant: shifts are never persisted.
- **`persist` flag on engine methods**: `set_trait`/`update_traits`/`lock_trait`/`unlock_trait` accept `persist: bool = False`. When True, the baseline is updated AND the state is saved to disk. When False (default), only `_current` moves — preserving backward compat with existing tests that call `set_trait` directly and expect `reset_traits()` to restore the config baseline.
- **Router `persist` flag**: `PUT /traits`, `POST /lock/{trait}`, `POST /unlock/{trait}` use `Query(True)` for `persist` — auto-save by default. Pass `?persist=false` for transient updates. The query-param approach (not body field) keeps it consistent across lock/unlock endpoints which have no body.
- **Singleton management**: added `get_engine()`/`set_engine()`/`reset_engine()` to the service module (mirrors voice_activation/task_manager pattern). Router uses `get_engine()` dynamically instead of importing `engine as default_engine` (which was a frozen reference that couldn't be swapped for tests).
- **Test injection**: `PersonalityEngine(config=fake_config, persistence_path=tmp_path/"personality.json")` — tests pass an explicit persistence path to isolate from the real `~/.ganesh/`. The `pers_path` fixture provides a temp path per test.
- **Concurrent modification gotcha**: the test file and router were partially modified by a previous incomplete attempt (referenced `save_state`/`load_state`/`is_persisted` methods that didn't exist in the service, and `personality_router.default_engine = test_engine` patching which doesn't work with `get_engine()`). Had to reconcile all three files. The `test_save_load_api_endpoints` test had flawed logic: it did a transient update (persist=false), then saved (which saves the BASELINE, not the transient value), then expected the transient value after load. Fixed by using persist=true for the saved update and persist=false for a separate transient update.
- **FastAPI TestClient query params**: `client.put("/path", json={...}, params={"persist": "false"})` — the `params` arg sets query string params. Values must be strings.
- **Frontend payload**: router now returns `persisted: boolean` in the payload. PersonalityPanel shows a "Saved"/"Not saved" badge and has Save/Load/Reset buttons in a single action row.
- Tests: 10 backend (5 existing + 5 new), 9 frontend (5 existing + 4 new). tsc clean.

## Wave 4: Multiple User Profiles + Shared Bridge Memory (Task 31)
- **Profile + bridge + audit persistence**: three SQLite tables across two DB files — `profiles.db` (profiles + active_profile singleton row) and `bridge.db` (bridge_grants + bridge_access_log). Profile IDs are UUID strings (stable, no auto-increment collision risk across re-imports).
- **Active profile tracking**: single-row `active_profile` table (id=1, profile_id TEXT). `ON CONFLICT(id) DO UPDATE` upsert pattern. First profile created is auto-activated; deleting the active profile re-activates the first remaining one.
- **Last-profile guard**: `delete_profile` raises `ValueError("Cannot delete the last remaining profile")` — router maps to 400. Frontend disables the delete button when `profiles.length <= 1`.
- **Memory scoping by profile_id**: `MemoryService.store/retrieve/update/delete/list` all accept `profile_id: Optional[str]`. Stored as a top-level field in the LanceDB payload JSON (alongside `content`, `user_metadata`, `created_at`, `updated_at`). Router resolves active profile via `get_profile_manager().get_active_profile_id()` when no explicit `?profile_id=` query param is passed.
- **LanceDB json_extract DOES NOT WORK on string payload columns**: `json_extract(payload, "$.key") = 'value'` fails with `Failed to coerce arguments to satisfy a call to 'json_extract'` because the payload column is `pa.string()` (Utf8), but `json_extract` expects `LargeBinary`. The existing `vector_store.list(filters=...)` path was never exercised with filters and is also broken. **Fix**: filter in Python post-retrieve. `retrieve_memories` over-fetches (`limit * 10`) then filters by `payload.get("profile_id") != profile_id` in Python. `list_memories` retrieves all then filters. This is MVP-acceptable; for large datasets, store `profile_id` as a separate LanceDB column instead.
- **Bridge grants are explicit per-memory**: `grant(granting, receiving, memory_id)` — no blanket access. `UNIQUE(granting, receiving, memory_id)` constraint. Bridge `query()` retrieves the granting profile's memories via `memory_service.retrieve_memories(profile_id=granting)`, then filters to only granted memory_ids. Audit log is written on EVERY query (even empty results / no grants).
- **Cascade deletion**: router-level cascade — `delete_profile` endpoint calls `memory_service.delete_memories_for_profile(id)` + `bridge_service.revoke_grants_for_profile(id)` BEFORE `profile_mgr.delete_profile(id)`. ProfileManager also has optional injected `MemoryDeleterProtocol`/`BridgeCascadeProtocol` hooks for service-level cascade (not wired by the router to avoid double-cascade).
- **Singleton pattern**: `get_profile_manager()`/`set_profile_manager()`/`reset_profile_manager()` and `get_bridge_service()`/`set_bridge_service()`/`reset_bridge_service()` — mirrors task_manager/personality. `check_same_thread=False` on the SQLite connection for FastAPI threadpool safety.
- **Prior attempt artifacts**: `profiles.py`, `bridge.py`, `routers/profiles.py`, `test_profiles.py`, `ProfileSwitcher.tsx`, and `ProfileSwitcher.test.tsx` already existed (untracked, from a prior incomplete attempt). Reconciled rather than rewrote: added cascade hooks to ProfileManager, added `delete_memories_for_profile` to MemoryService, fixed the LanceDB json_extract filter bug by switching to Python filtering.
- **Frontend ProfileSwitcher**: standalone panel component (not wired into App.tsx — consistent with PersonalityPanel). Dropdown list with activate-on-click, create form (name/desc/color), inline edit, delete with `window.confirm`, bridge grant create/revoke, bridge query with results display, audit log viewer. 8 vitest tests covering create/activate/delete/grant/revoke/query/error.
- Tests: 6 backend (`test_profiles.py`) + 8 frontend (`ProfileSwitcher.test.tsx`). Full suite: 133 backend + 164 frontend passing. tsc clean.

## Wave 4: Multiple User Profiles + Shared Bridge Memory (Task 31)
- **ProfileManager** (`services/profiles.py`): SQLite-backed profile CRUD with `active_profile` singleton row (id=1). First profile auto-activates. Last profile cannot be deleted (raises ValueError → 400). Uses `check_same_thread=False` for FastAPI threadpool safety. Singleton pattern: `get_profile_manager()` / `set_profile_manager()` / `reset_profile_manager()`.
- **BridgeService** (`services/bridge.py`): explicit per-memory cross-profile grants. `grant()` refuses self-grants. `query()` retrieves a generous pool (limit*10) of the granting profile's memories via MemoryService.retrieve_memories(profile_id=...), then filters to only granted memory_ids. Every query (including no-grant queries) logs to `bridge_access_log`. `revoke_grants_for_profile()` is the cascade helper called by the router on profile deletion.
- **Memory scoping**: MemoryService.store_memory/retrieve_memories/list_memories now accept `profile_id: Optional[str]`. Stored as a top-level field in the LanceDB payload JSON. The memory router reads the active profile from ProfileManager via `_resolve_profile_id()` (falls back to None if no profile manager — backward compat for standalone memory tests).
- **LanceDB filter limitation**: `json_extract(payload, "$.key")` does NOT work on Utf8 payload columns (LanceDB requires LargeBinary). The vector_store's `search` and `list` methods now do post-retrieval filtering in Python instead of SQL-level filters. `search` fetches `top_k * 20` rows when filters are applied to ensure enough results survive post-filtering.
- **Cascade ordering**: the profiles router deletes memories + grants BEFORE the profile row (so the profile still exists when cascade helpers run). `memory_service.delete_memories_for_profile(profile_id)` lists then deletes each memory. `bridge_service.revoke_grants_for_profile(profile_id)` deletes grants where the profile is granter OR receiver.
- **Router structure**: profiles router has a sub-router (`bridge_router`) mounted under `/api/profiles/bridge` via `router.include_router(bridge_router)`. Both share the `/api/profiles` prefix. Bridge endpoints: POST /grant, DELETE /grant/{id}, GET /grant, GET /query, GET /audit.
- **Frontend ProfileSwitcher**: single component with profile list (activate/delete), create form (name + color picker + description), bridge grant form (granting/receiving profile dropdowns + memory ID), grant list with revoke, bridge query (target profile + semantic query + results), and audit log. Uses `sidecarFetch` mock pattern. 8 tests cover render, create, activate, delete, grant, revoke, query, error.
- **Test mock sequencing**: the component fires 3 fetches on mount (profiles, grants, audit) — tests must mock all 3 in order with `mockResolvedValueOnce`. Action-triggered refreshes also consume mocks in the same order.
- No new native deps — SQLite is stdlib, LanceDB already registered. No NATIVE_DEPS.md update needed.
- Tests: 6 backend (test_profiles.py), 8 frontend (ProfileSwitcher.test.tsx). Full suite: 133 backend + 164 frontend passing. tsc clean.
## Memory Service Fix
- Removed duplicate method definitions in memory.py that were introduced during profile scoping.
- Verified that the profile-aware versions of the methods were retained.

## Task 32: Ambient Idle Animation (Visualizer Idle State)
- `VisualizerState` is a union type (`'IDLE' | 'THINKING' | 'SPEAKING'`), not an enum — simpler and more idiomatic TypeScript.
- `RenderParams` fields `state` and `timeMs` are **optional** for backward compatibility — existing plugins that don't destructure them still compile and work.
- State machine in `VisualizerCanvas`: auto-detects SPEAKING when audio energy > 0.02 threshold, debounced return to IDLE after 300ms (via `setTimeout`). Forced `state` prop from parent overrides auto-detection entirely.
- `timeMs` is computed as `rafTimestamp - stateStartTimeRef.current` — passed directly to render, no useState needed (avoids unnecessary re-renders).
- Idle animation: 0.1Hz sine wave with 5% amplitude modulation (barely visible, CPU-light). Thinking: 1Hz pulse with 1.5x amplitude. Both use `Math.sin(timeSec * freq * PI * 2)` pattern.
- **Test gotcha**: `fireAll()` only fires raf callbacks registered at call time — the raf loop re-schedules itself, so subsequent frames need separate `fireAll()` calls. State updates from raf callbacks need `act()` wrapping for React to flush.
- **Test gotcha**: The IDLE→SPEAKING→IDLE transition uses a 300ms `setTimeout` debounce. Tests that verify the IDLE return must advance fake timers past the debounce threshold.
- **Pre-existing test fix**: `waveform-render.test.ts` expected empty audio = no drawing. Now empty audio triggers idle animation (draws sine wave). Updated test to expect `moveTo` calls for IDLE state, and added a separate test for SPEAKING state with empty audio (no drawing).
- All 176 tests pass, tsc --noEmit clean.

## Task 32: Ambient Idle Animation (Visualizer Idle State)
- `VisualizerState` type: `'IDLE' | 'THINKING' | 'SPEAKING'` — string literal union (not enum) for easy serialization and extensibility.
- `RenderParams` extended with `state: VisualizerState` and `timeMs: number` — backward-compatible since existing plugins destructure only what they need.
- `VisualizerCanvas` state machine: auto-detects audio activity via energy threshold (0.02 average amplitude). Transitions IDLE → SPEAKING immediately on activity, SPEAKING → IDLE after 300ms debounce (setTimeout).
- `state` prop on `VisualizerCanvas` and `VoiceVisualizer` allows parent override (for future thinking indicator integration).
- WaveformVisualizer idle: 0.1Hz sine wave with 3% height amplitude, opacity 0.3-0.45 — subtle breathing effect.
- WaveformVisualizer thinking: 1Hz sine wave with 8% height amplitude, opacity 0.5-0.8 — faster, more visible pulse.
- FreqBarsVisualizer idle: gentle wave-modulated bars at 15% max height, low opacity.
- ParticleVisualizer idle: pulsing radial gradient glow at center (no particle spawning).
- HoloFaceVisualizer idle: slow rotation + minimal vertex displacement, resets to original positions.
- **Test gotcha**: `waitFor` + `vi.useFakeTimers()` = timeout. `waitFor` polls on real intervals but fake timers block the event loop. Solution: use `act()` + direct assertions for sync state checks, or enable fake timers only for specific tests that need `vi.advanceTimersByTime()`.
- **TypeScript gotcha**: `_elapsedMs` pattern for unused state setter — prefix with `_` to satisfy TS no-unused-vars without removing the state (needed for `setElapsedMs` call).
- All 176 tests pass, tsc --noEmit clean.

## Task 32: Ambient Idle Animation (Visualizer Idle State)
- `VisualizerState` type: `'IDLE' | 'THINKING' | 'SPEAKING'` — string literal union (not enum) for easy serialization and extensibility.
- `RenderParams` extended with `state: VisualizerState` and `timeMs: number` — backward-compatible since existing plugins destructure only what they need.
- `VisualizerCanvas` state machine: auto-detects audio activity via energy threshold (0.02 average amplitude). Transitions IDLE → SPEAKING immediately on activity, SPEAKING → IDLE after 300ms debounce (setTimeout).
- `state` prop on `VisualizerCanvas` and `VoiceVisualizer` allows parent override (for future thinking indicator integration).
- WaveformVisualizer idle: 0.1Hz sine wave with 3% height amplitude, opacity 0.3-0.45 — subtle breathing effect.
- WaveformVisualizer thinking: 1Hz sine wave with 8% height amplitude, opacity 0.5-0.8 — faster, more visible pulse.
- FreqBarsVisualizer idle: gentle wave-modulated bars at 15% max height, low opacity.
- ParticleVisualizer idle: pulsing radial gradient glow at center (no particle spawning).
- HoloFaceVisualizer idle: slow rotation + minimal vertex displacement, resets to original positions.
- **Test gotcha**: `waitFor` + `vi.useFakeTimers()` = timeout. `waitFor` polls on real intervals but fake timers block the event loop. Solution: use `act()` + direct assertions for sync state checks, or enable fake timers only for specific tests that need `vi.advanceTimersByTime()`.
- **TypeScript gotcha**: `_elapsedMs` pattern for unused state setter — prefix with `_` to satisfy TS no-unused-vars without removing the state (needed for `setElapsedMs` call).
- All 176 tests pass, tsc --noEmit clean.
