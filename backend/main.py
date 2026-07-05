"""Ganesh backend sidecar entry point.

A FastAPI application spawned by the Tauri shell as a child process. The sidecar
binds to an ephemeral port on the loopback interface and writes the chosen port
to stdout in the parseable format ``PORT: <port>`` so the host can read it.

CLI flags:
    --check-imports   Import all registered native dependencies and exit 0/1.
"""
from __future__ import annotations

import argparse
import signal
import socket
import sys
import threading
from contextlib import asynccontextmanager
from typing import AsyncIterator, Sequence

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ganesh_backend.routers import memory as memory_router

from ganesh_backend.routers import files as files_router

from ganesh_backend.routers import search as search_router

from ganesh_backend.routers import chat as chat_router
from ganesh_backend.routers.config import router as config_router

# Tauri v2 webview origins. On Windows the webview uses https://tauri.localhost,
# on Linux/macOS it uses tauri://localhost. Both must be allowed for CORS.
TAURI_ORIGINS: tuple[str, ...] = (
    "tauri://localhost",
    "https://tauri.localhost",
)

# Loopback only — never expose the sidecar on a public interface.
# Port 0 asks the OS for an ephemeral free port (never hardcoded).
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 0

# Registry of native / critical Python dependencies verified by --check-imports.
# Add new native deps here as they are introduced (Wave 2+ voice/memory stack).
NATIVE_DEPS: tuple[str, ...] = (
    "fastapi",
    "uvicorn",
    "pydantic",
    "litellm",
    "keyring",
    "yaml",  # PyYAML exposes the `yaml` module, not `pyyaml`
    "lancedb",
    "mem0",
)

# A threading.Event coordinates shutdown between the /shutdown endpoint and the
# SIGTERM/SIGINT handlers without calling os._exit (which would skip lifespan
# cleanup). The watchdog thread watches this event and stops the uvicorn server.
shutdown_event = threading.Event()


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        shutdown_event.set()

    app = FastAPI(title="Ganesh API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(TAURI_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(search_router.router)

    app.include_router(files_router.router)

    app.include_router(chat_router.router, prefix="/api")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(config_router)

    @app.post("/shutdown")
    async def shutdown() -> dict[str, str]:
        # Defer the stop to a background thread so this HTTP response is
        # flushed before the server begins shutting down.
        threading.Thread(target=_trigger_shutdown, daemon=True).start()
        return {"status": "shutting down"}

    app.include_router(memory_router.router)

    return app


def _trigger_shutdown() -> None:
    shutdown_event.set()


class GaneshServer(uvicorn.Server):
    """uvicorn.Server subclass that prints the bound port to stdout.

    After uvicorn binds its sockets we read the actual port (which may differ
    from the requested one when port 0 was requested) and emit a single
    parseable line ``PORT: <port>`` so the Tauri host can connect.
    """

    def __init__(self, config: uvicorn.Config) -> None:
        super().__init__(config)
        self._port_printed = False

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        if not self._port_printed:
            port = self._bound_port()
            if port is not None:
                # Flush is critical: Tauri reads stdout via a pipe and may
                # otherwise buffer this line indefinitely, deadlocking startup.
                print(f"PORT: {port}", flush=True)
                self._port_printed = True

    def _bound_port(self) -> int | None:
        for server in self.servers:
            for sock in server.sockets:
                name = sock.getsockname()
                if name and len(name) >= 2:
                    return int(name[1])
        return None


def build_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> GaneshServer:
    config = uvicorn.Config(
        app=create_app(),
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="on",
    )
    return GaneshServer(config)


def _install_signal_handlers(server: uvicorn.Server) -> None:
    def _handler(signum: int, _frame: object) -> None:
        shutdown_event.set()
        server.should_exit = True

    # SIGTERM: sent by Tauri when the app is closing.
    signal.signal(signal.SIGTERM, _handler)
    # SIGINT: sent on Ctrl-C in dev.
    signal.signal(signal.SIGINT, _handler)


def _watchdog(server: uvicorn.Server) -> None:
    shutdown_event.wait()
    server.should_exit = True


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> int:
    server = build_server(host=host, port=port)
    _install_signal_handlers(server)
    threading.Thread(target=_watchdog, daemon=True, args=(server,)).start()
    server.run()
    return 0


def check_imports() -> int:
    """Import every registered native dependency; exit 0 on success, 1 on failure."""
    failures: list[tuple[str, str]] = []
    for dep in NATIVE_DEPS:
        try:
            __import__(dep)
        except ImportError as exc:
            failures.append((dep, str(exc)))

    if failures:
        for dep, err in failures:
            print(f"FAIL: {dep}: {err}", file=sys.stderr)
        return 1

    print("All native dependencies imported successfully")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ganesh-backend",
        description="Ganesh FastAPI sidecar.",
    )
    parser.add_argument(
        "--check-imports",
        action="store_true",
        help="Import all registered native dependencies and exit 0/1.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Bind host (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="Bind port; 0 = ephemeral (default: 0)",
    )
    args = parser.parse_args(argv)

    if args.check_imports:
        return check_imports()

    return run_server(host=args.host, port=args.port)


# Module-level `app` for `uvicorn main:app` style invocation in dev.
app = create_app()


if __name__ == "__main__":
    sys.exit(main())
