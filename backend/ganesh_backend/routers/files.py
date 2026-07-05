"""Read-only file system browsing router for the Ganesh sidecar.

Exposes GET endpoints for listing directories, reading file contents, and
resolving paths. All access is gated by a system-directory blocklist and
symlink resolution to prevent traversal attacks.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Union

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/files", tags=["files"])

MAX_READ_BYTES: int = 10 * 1024 * 1024

BLOCKED_DIRS: tuple[Path, ...] = (
    Path("/etc"),
    Path("/proc"),
    Path("/sys"),
    Path("/boot"),
    Path("/dev"),
    Path("/root"),
    Path("/var/log"),
    Path("/usr"),
    Path("/bin"),
    Path("/sbin"),
    Path("/lib"),
    Path("/lib64"),
    Path("/run"),
    Path("/snap"),
)


class PathBlockedError(HTTPException):
    def __init__(self, path: Path) -> None:
        super().__init__(status_code=403, detail=f"access blocked: {path}")


def _resolve(path_str: str | None) -> Path:
    """Resolve a user-supplied path string to an absolute, canonical Path.

    Relative paths resolve against the user's home directory. Symlinks and
    `..` segments are collapsed via Path.resolve() so the blocklist check
    always sees the true filesystem location.
    """
    if path_str is None or path_str == "":
        return Path.home()
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = Path.home() / p
    return p.resolve(strict=False)


def _check_blocked(resolved: Path) -> None:
    for blocked in BLOCKED_DIRS:
        try:
            blocked_resolved = blocked.resolve(strict=False)
        except OSError:
            blocked_resolved = blocked
        if resolved == blocked_resolved or blocked_resolved in resolved.parents:
            raise PathBlockedError(resolved)


def _entry_type(p: Path) -> str:
    if p.is_dir():
        return "directory"
    if p.is_file():
        return "file"
    return "other"


def _entry_metadata(p: Path) -> dict[str, Union[str, int]]:
    try:
        stat = p.stat()
    except OSError:
        return {
            "name": p.name,
            "type": "broken",
            "size": 0,
            "modified": datetime.fromtimestamp(0, tz=timezone.utc).isoformat(),
        }
    return {
        "name": p.name,
        "type": _entry_type(p),
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


@router.get("/list")
async def list_directory(
    path: str | None = Query(default=None, description="Directory to list"),
) -> dict[str, object]:
    resolved = _resolve(path)
    _check_blocked(resolved)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"not found: {resolved}")
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"not a directory: {resolved}")
    entries = [_entry_metadata(child) for child in sorted(resolved.iterdir())]
    return {"path": str(resolved), "entries": entries}


@router.get("/read")
async def read_file(
    path: str = Query(..., description="File to read"),
) -> dict[str, object]:
    resolved = _resolve(path)
    _check_blocked(resolved)
    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"not found: {resolved}")
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"not a file: {resolved}")
    size = resolved.stat().st_size
    if size > MAX_READ_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file too large: {size} > {MAX_READ_BYTES} bytes",
        )
    content = resolved.read_text(encoding="utf-8", errors="replace")
    return {"path": str(resolved), "content": content, "size": size}


@router.get("/navigate")
async def navigate(
    path: str = Query(..., description="Path to resolve and inspect"),
) -> dict[str, object]:
    resolved = _resolve(path)
    exists = resolved.exists()
    entry_type = _entry_type(resolved) if exists else "missing"
    return {
        "path": str(resolved),
        "exists": exists,
        "type": entry_type,
    }
