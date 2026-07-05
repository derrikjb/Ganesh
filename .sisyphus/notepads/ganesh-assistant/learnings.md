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
