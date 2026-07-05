"""Tests for the files router (file system browsing tool).

Covers GET /api/files/list, /read, /navigate plus security blocks for
system directories, symlink escapes, and `../` traversal attacks.
"""
from __future__ import annotations

import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main as main_module
from ganesh_backend.routers import files as files_router

BACKEND_DIR = Path(__file__).resolve().parent.parent
VENV_PYTHON = BACKEND_DIR / "venv" / "bin" / "python"


@pytest.fixture(autouse=True)
def _reset_shutdown_event():
    main_module.shutdown_event.clear()
    yield
    main_module.shutdown_event.clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(main_module.create_app())


@pytest.fixture()
def tmp_workspace(tmp_path: Path) -> Path:
    (tmp_path / "alpha.txt").write_text("hello alpha")
    (tmp_path / "beta.log").write_text("beta contents\nsecond line\n")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "nested.md").write_text("# nested")
    return tmp_path


def test_list_directory(client: TestClient, tmp_workspace: Path) -> None:
    response = client.get("/api/files/list", params={"path": str(tmp_workspace)})
    assert response.status_code == 200
    data = response.json()
    assert data["path"] == str(tmp_workspace)
    names = {entry["name"] for entry in data["entries"]}
    assert names == {"alpha.txt", "beta.log", "subdir"}
    for entry in data["entries"]:
        assert "name" in entry
        assert "type" in entry
        assert "size" in entry
        assert "modified" in entry
    dir_entry = next(e for e in data["entries"] if e["name"] == "subdir")
    assert dir_entry["type"] == "directory"


def test_list_directory_default_home(client: TestClient) -> None:
    response = client.get("/api/files/list")
    assert response.status_code == 200
    data = response.json()
    assert data["path"] == str(Path.home())


def test_list_directory_not_found(client: TestClient, tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    response = client.get("/api/files/list", params={"path": str(missing)})
    assert response.status_code == 404


def test_list_directory_on_file_returns_400(
    client: TestClient, tmp_workspace: Path
) -> None:
    target = tmp_workspace / "alpha.txt"
    response = client.get("/api/files/list", params={"path": str(target)})
    assert response.status_code == 400


def test_read_file(client: TestClient, tmp_workspace: Path) -> None:
    target = tmp_workspace / "beta.log"
    response = client.get("/api/files/read", params={"path": str(target)})
    assert response.status_code == 200
    data = response.json()
    assert data["path"] == str(target)
    assert data["content"] == "beta contents\nsecond line\n"
    assert data["size"] == len("beta contents\nsecond line\n")


def test_read_file_not_found(client: TestClient, tmp_path: Path) -> None:
    missing = tmp_path / "nope.txt"
    response = client.get("/api/files/read", params={"path": str(missing)})
    assert response.status_code == 404


def test_read_file_too_large(client: TestClient, tmp_path: Path) -> None:
    big = tmp_path / "big.bin"
    big.write_bytes(b"\x00" * (files_router.MAX_READ_BYTES + 1))
    response = client.get("/api/files/read", params={"path": str(big)})
    assert response.status_code == 413


def test_read_file_on_directory_returns_400(
    client: TestClient, tmp_workspace: Path
) -> None:
    response = client.get("/api/files/read", params={"path": str(tmp_workspace)})
    assert response.status_code == 400


def test_navigate_existing(client: TestClient, tmp_workspace: Path) -> None:
    target = tmp_workspace / "alpha.txt"
    response = client.get("/api/files/navigate", params={"path": str(target)})
    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is True
    assert data["path"] == str(target)
    assert data["type"] == "file"


def test_navigate_missing(client: TestClient, tmp_path: Path) -> None:
    target = tmp_path / "ghost"
    response = client.get("/api/files/navigate", params={"path": str(target)})
    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is False


def test_navigate_relative(client: TestClient, tmp_workspace: Path) -> None:
    response = client.get(
        "/api/files/navigate", params={"path": "some/relative/path"}
    )
    assert response.status_code == 200
    data = response.json()
    expected = str(Path.home() / "some" / "relative" / "path")
    assert data["path"] == expected


@pytest.mark.parametrize(
    "system_path",
    ["/etc", "/proc", "/sys", "/boot", "/dev"],
)
def test_block_system_dir(client: TestClient, system_path: str) -> None:
    response = client.get("/api/files/list", params={"path": system_path})
    assert response.status_code == 403


@pytest.mark.parametrize(
    "system_path",
    ["/etc/passwd", "/proc/self/status"],
)
def test_block_system_read(client: TestClient, system_path: str) -> None:
    response = client.get("/api/files/read", params={"path": system_path})
    assert response.status_code == 403


def test_directory_traversal_protection_list(
    client: TestClient, tmp_workspace: Path
) -> None:
    """`../` traversal landing in a blocked system directory must be 403.

    Security-critical: verifies the resolver canonicalizes the path via
    Path.resolve() before the blocked-dir check, so encoded/relative escapes
    cannot bypass the allowlist.
    """
    evil = Path("/tmp/../etc")
    response = client.get("/api/files/list", params={"path": str(evil)})
    assert response.status_code == 403


def test_directory_traversal_protection_read(
    client: TestClient, tmp_workspace: Path
) -> None:
    evil = Path("/tmp/../etc/passwd")
    response = client.get("/api/files/read", params={"path": str(evil)})
    assert response.status_code == 403


def test_symlink_escape_blocked(client: TestClient, tmp_path: Path) -> None:
    """Symlinks are resolved before the blocked-dir check so a link pointing
    at /etc cannot be used to bypass the allowlist."""
    link = tmp_path / "evil_link"
    link.symlink_to("/etc")
    response = client.get("/api/files/list", params={"path": str(link)})
    assert response.status_code == 403


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
        if text.startswith("PORT:"):
            return int(text.split(":")[1].strip())
    raise TimeoutError(f"no PORT line after {timeout}s")


def test_live_sidecar_file_browsing(tmp_workspace: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_DIR)
    proc = subprocess.Popen(
        [str(VENV_PYTHON), str(BACKEND_DIR / "main.py")],
        cwd=str(BACKEND_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        port = _wait_for_port_line(proc)
        deadline = time.monotonic() + 10.0
        url = f"http://127.0.0.1:{port}/health"
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError("sidecar never became healthy")

        list_url = (
            f"http://127.0.0.1:{port}/api/files/list?path="
            f"{urllib.parse.quote(str(tmp_workspace))}"
        )
        with urllib.request.urlopen(list_url, timeout=5) as resp:
            assert resp.status == 200

        etc_url = (
            f"http://127.0.0.1:{port}/api/files/list?path="
            f"{urllib.parse.quote('/etc')}"
        )
        try:
            urllib.request.urlopen(etc_url, timeout=5)
            raise AssertionError("expected 403 for /etc")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
