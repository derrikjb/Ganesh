# Ganesh AI Assistant

Ganesh is a local-first, privacy-focused AI assistant built with Tauri, React, and FastAPI.

## Project Structure

- `backend/`: FastAPI server handling LLM orchestration and memory.
- `frontend/`: Vite + React + TypeScript + Tailwind CSS desktop UI.
- `src-tauri/`: Tauri v2 core for native integration.
- `docs/`: Project documentation.

## Tech Stack

- **Frontend**: React 18, TypeScript, Tailwind CSS, Vitest
- **Backend**: Python 3.10+, FastAPI, LiteLLM, Pydantic, Pytest
- **Desktop**: Tauri v2 (Rust)
- **OS Support**: Windows, Linux (Dark Theme Only)

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.10+
- Rust (latest stable)
- Native dependencies (see `docs/NATIVE_DEPS.md`)

### Development

1. Install frontend dependencies: `cd frontend && npm install`
2. Install backend dependencies: `cd backend && pip install -e ".[dev]"`
3. Run Tauri dev: `npm run tauri dev`
