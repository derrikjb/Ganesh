"""Tests for the dynamic plugin system (loader + registry + router).

Covers:
    - test_plugin_discovery — discovers plugins in a directory
    - test_plugin_load       — loads a plugin from its manifest
    - test_plugin_invoke     — invokes a plugin tool via the registry
    - test_plugin_hot_reload — reloads plugins after a source change

All tests use a temp plugins directory and a temp GANESH_DATA_DIR so the
real ``~/.ganesh/`` is never touched.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from ganesh_backend.services.plugin_loader import (  # noqa: E402
    PluginLoader,
)
from ganesh_backend.services.plugin_registry import (  # noqa: E402
    PluginRegistry,
)
from ganesh_backend.routers import plugins as plugins_router  # noqa: E402
from main import create_app  # noqa: E402


EXAMPLE_MANIFEST = {
    "name": "example",
    "version": "0.1.0",
    "description": "test note-taker",
    "entry_point": "register",
    "tools": [
        {
            "name": "take_note",
            "description": "Save a short note to disk.",
            "parameters": {"text": {"type": "string", "required": True}},
        }
    ],
}

EXAMPLE_PLUGIN_PY = '''
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _notes_dir() -> Path:
    env_dir = os.environ.get("GANESH_DATA_DIR")
    base = Path(env_dir) if env_dir else Path.home() / ".ganesh"
    return base / "notes"


def take_note(text: str) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    notes_dir = _notes_dir()
    notes_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = notes_dir / f"note-{stamp}.txt"
    path.write_text(text, encoding="utf-8")
    return {"path": str(path), "chars": len(text)}


def register(registry, manifest) -> None:
    for tool in manifest["tools"]:
        if tool["name"] == "take_note":
            registry.register_tool(
                plugin_name=manifest["name"],
                tool_name="take_note",
                fn=take_note,
                schema=tool,
            )
'''


@pytest.fixture
def plugins_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temp plugins dir and point GANESH_DATA_DIR at it."""

    data_dir = tmp_path / "ganesh_data"
    data_dir.mkdir()
    monkeypatch.setenv("GANESH_DATA_DIR", str(data_dir))
    plugins_dir = data_dir / "plugins"
    plugins_dir.mkdir()
    return plugins_dir


def _write_example_plugin(plugins_dir: Path) -> Path:
    plugin_dir = plugins_dir / "example"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.json").write_text(
        json.dumps(EXAMPLE_MANIFEST), encoding="utf-8"
    )
    (plugin_dir / "plugin.py").write_text(EXAMPLE_PLUGIN_PY, encoding="utf-8")
    return plugin_dir / "manifest.json"


@pytest.fixture
def fresh_registry() -> PluginRegistry:
    return PluginRegistry()


@pytest.fixture
def loader(plugins_root: Path, fresh_registry: PluginRegistry) -> PluginLoader:
    return PluginLoader(plugins_dir=plugins_root, registry=fresh_registry)


@pytest.fixture
def client(
    loader: PluginLoader, fresh_registry: PluginRegistry
) -> TestClient:
    """FastAPI TestClient wired to the temp loader + registry."""

    plugins_router.set_router_singletons(loader, fresh_registry)
    app = create_app()
    try:
        yield TestClient(app)
    finally:
        plugins_router.reset_router_singletons()


def test_plugin_discovery(loader: PluginLoader, plugins_root: Path) -> None:
    """discover_plugins() returns the manifest path for a present plugin."""

    assert loader.discover_plugins() == []
    manifest = _write_example_plugin(plugins_root)
    found = loader.discover_plugins()
    assert len(found) == 1
    assert found[0].resolve() == manifest.resolve()


def test_plugin_load(loader: PluginLoader, plugins_root: Path) -> None:
    """load_plugin() registers the plugin and its tool with the registry."""

    _write_example_plugin(plugins_root)
    loaded = loader.load_all()
    assert len(loaded) == 1
    assert loaded[0].name == "example"
    assert loaded[0].version == "0.1.0"

    reg = loader.registry
    plugins = reg.list_plugins()
    assert len(plugins) == 1
    assert plugins[0].name == "example"

    tools = reg.list_tools()
    assert len(tools) == 1
    assert tools[0].qualified_name == "example.take_note"
    assert tools[0].schema["name"] == "take_note"


def test_plugin_invoke(loader: PluginLoader, plugins_root: Path) -> None:
    """Invoking a registered tool runs the callable and returns its result."""

    _write_example_plugin(plugins_root)
    loader.load_all()

    reg = loader.registry
    entry = reg.get_tool("example.take_note")
    assert entry is not None
    result = entry.fn(text="hello world")
    assert result["chars"] == len("hello world")
    note_path = Path(result["path"])
    assert note_path.exists()
    assert note_path.read_text(encoding="utf-8") == "hello world"
    assert note_path.parent.name == "notes"


def test_plugin_hot_reload(
    loader: PluginLoader, plugins_root: Path
) -> None:
    """reload_plugins() picks up source changes without a restart."""

    _write_example_plugin(plugins_root)
    loader.load_all()
    reg = loader.registry
    assert reg.get_tool("example.take_note") is not None

    plugin_py = plugins_root / "example" / "plugin.py"
    src = plugin_py.read_text(encoding="utf-8")
    src = src.replace(
        'return {"path": str(path), "chars": len(text)}',
        'return {"path": str(path), "chars": len(text) * 2}',
    )
    plugin_py.write_text(src, encoding="utf-8")

    loaded = loader.reload_plugins()
    assert len(loaded) == 1
    entry = reg.get_tool("example.take_note")
    assert entry is not None
    result = entry.fn(text="abc")
    assert result["chars"] == 6


def test_router_list_and_invoke(
    client: TestClient, plugins_root: Path
) -> None:
    _write_example_plugin(plugins_root)
    loader = plugins_router.get_loader()
    loader.load_all()

    r = client.get("/api/plugins")
    assert r.status_code == 200
    body = r.json()
    assert len(body["plugins"]) == 1
    assert body["plugins"][0]["name"] == "example"

    r = client.get("/api/plugins/tools")
    assert r.status_code == 200
    tools = r.json()["tools"]
    assert len(tools) == 1
    assert tools[0]["qualified_name"] == "example.take_note"
    r = client.post(
        "/api/plugins/example/take_note/invoke",
        json={"parameters": {"text": "via http"}},
    )
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["chars"] == len("via http")
    assert Path(result["path"]).read_text(encoding="utf-8") == "via http"

    r = client.post("/api/plugins/reload")
    assert r.status_code == 200
    assert "example" in r.json()["reloaded"]
