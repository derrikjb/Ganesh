"""Example Ganesh plugin: a simple note-taker.

Implements the ``take_note`` tool declared in ``manifest.json``. Notes are
saved as timestamped text files under ``~/.ganesh/notes/`` (or
``$GANESH_DATA_DIR/notes/`` when the env override is set).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ganesh_backend.services.plugin_registry import PluginRegistry


def _notes_dir() -> Path:
    env_dir = os.environ.get("GANESH_DATA_DIR")
    base = Path(env_dir) if env_dir else Path.home() / ".ganesh"
    return base / "notes"


def take_note(text: str) -> dict[str, Any]:
    """Save ``text`` to a timestamped file and return its path."""

    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")

    notes_dir = _notes_dir()
    notes_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = notes_dir / f"note-{stamp}.txt"
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "chars": len(text)}


def register(registry: PluginRegistry, manifest: dict[str, Any]) -> None:
    """Wire the manifest's tools to their implementing callables."""

    for tool in manifest["tools"]:
        if tool["name"] == "take_note":
            registry.register_tool(
                plugin_name=manifest["name"],
                tool_name="take_note",
                fn=take_note,
                schema=tool,
            )
