"""Tests for the Ganesh sidecar FastAPI app.

Covers:
    - GET /health returns 200 + {"status": "ok"}
    - CORS headers present for tauri://localhost origin
    - Ephemeral port binding (port 0 → OS-assigned, reported via stdout)
    - POST /shutdown triggers graceful exit
    - --check-imports CLI flag exits 0 and verifies native deps
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main as main_module

BACKEND_DIR = Path(__file__).resolve().parent.parent
MAIN_PY = BACKEND_DIR / "main.py"
VENV_PYTHON = BACKEND_DIR / "venv" / "bin" / "python"


@pytest.fixture(autouse=True)
def _reset_shutdown_event():
    main_module.shutdown_event.clear()
    yield
    main_module.shutdown_event.clear()


def test_health_endpoint():
    client = TestClient(main_module.create_app())
    with client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_configured():
    client = TestClient(main_module.create_app())
    with client:
        response = client.get(
            "/health",
            headers={"Origin": "tauri://localhost"},
        )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "tauri://localhost"


def test_cors_configured_https_origin():
    client = TestClient(main_module.create_app())
    with client:
        response = client.get(
            "/health",
            headers={"Origin": "https://tauri.localhost"},
        )
    assert response.status_code == 200
    assert (
        response.headers.get("access-control-allow-origin")
        == "https://tauri.localhost"
    )


def _wait_for_port_line(proc: subprocess.Popen, timeout: float = 10.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                raise RuntimeError(
                    f"sidecar exited early rc={proc.returncode} "
                    f"stderr={proc.stderr.read().decode() if proc.stderr else ''}"
                )
            continue
        text = line.decode().strip()
        match = re.match(r"^PORT:\s*(\d+)$", text)
        if match:
            return int(match.group(1))
    raise TimeoutError(f"no PORT line after {timeout}s")


def _wait_for_health(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    url = f"http://127.0.0.1:{port}/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(0.1)
    raise RuntimeError(f"health check failed on {url}: {last_err}")


def test_ephemeral_port():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_DIR)
    proc = subprocess.Popen(
        [str(VENV_PYTHON), str(MAIN_PY)],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        port = _wait_for_port_line(proc)
        # Port 0 means "unassigned" — a real bound port is always > 0.
        assert port > 0, f"expected real port, got {port}"
        # Confirm the port is actually listening on loopback.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            s.connect(("127.0.0.1", port))
        _wait_for_health(port)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def test_shutdown_endpoint():
    client = TestClient(main_module.create_app())
    with client:
        response = client.post("/shutdown")
        assert response.status_code == 200
        assert response.json() == {"status": "shutting down"}
    # After the response, the shutdown event must be set so the watchdog
    # stops the uvicorn server.
    assert main_module.shutdown_event.is_set()


def test_check_imports():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_DIR)
    result = subprocess.run(
        [str(VENV_PYTHON), str(MAIN_PY), "--check-imports"],
        cwd=str(BACKEND_DIR),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"--check-imports failed rc={result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "All native dependencies imported successfully" in result.stdout
