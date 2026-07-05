"""Dynamic plugin loader: discovers and loads plugins from the filesystem.

A *plugin* is a directory containing:

* ``manifest.json`` — declarative metadata + tool schemas
* ``plugin.py``    — Python module implementing the tool callables

Manifest schema::

    {
        "name": "example",
        "version": "0.1.0",
        "description": "An example plugin",
        "entry_point": "register",          # name of the registration fn
        "tools": [
            {
                "name": "take_note",
                "description": "Save a short note to disk",
                "parameters": {"text": {"type": "string", "required": True}}
            }
        ]
    }

The ``entry_point`` is a callable inside ``plugin.py`` with the signature::

    def register(registry: PluginRegistry, manifest: dict) -> None

It is responsible for calling ``registry.register_tool(...)`` for each
declared tool, wiring the manifest's tool schema to the implementing callable.

Plugins live under ``~/.ganesh/plugins/`` (override via ``GANESH_DATA_DIR``).
Hot-reload re-scans the directory and replaces all registered plugins.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Optional

from ganesh_backend.services.plugin_registry import (
    PluginEntry,
    PluginRegistry,
    get_registry,
)

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.json"
PLUGIN_FILENAME = "plugin.py"

MANIFEST_FILENAME = "manifest.json"
PLUGIN_FILENAME = "plugin.py"

REQUIRED_MANIFEST_KEYS = ("name", "version", "description", "entry_point", "tools")


def _default_plugins_dir() -> Path:
    """Resolve the plugins root from ``GANESH_DATA_DIR`` or ``~/.ganesh``."""

    env_dir = os.environ.get("GANESH_DATA_DIR")
    base = Path(env_dir) if env_dir else Path.home() / ".ganesh"
    return base / "plugins"


class PluginLoader:
    """Discovers and loads plugins from a directory tree into a registry."""

    def __init__(
        self,
        plugins_dir: Optional[Path] = None,
        registry: Optional[PluginRegistry] = None,
    ) -> None:
        self._plugins_dir = Path(plugins_dir) if plugins_dir else _default_plugins_dir()
        self._registry = registry if registry is not None else get_registry()
        self._lock = threading.RLock()
        self._loaded_modules: dict[str, Any] = {}

    @property
    def plugins_dir(self) -> Path:
        return self._plugins_dir

    @property
    def registry(self) -> PluginRegistry:
        return self._registry

    def discover_plugins(self) -> list[Path]:
        """Return absolute paths to every ``manifest.json`` under plugins_dir.

        A plugin directory is any subdirectory of ``plugins_dir`` that
        contains both ``manifest.json`` and ``plugin.py``. The plugins_dir
        itself is NOT scanned for a manifest (only its children).
        """

        if not self._plugins_dir.is_dir():
            return []

        found: list[Path] = []
        for child in sorted(self._plugins_dir.iterdir()):
            if not child.is_dir():
                continue
            manifest = child / MANIFEST_FILENAME
            plugin_py = child / PLUGIN_FILENAME
            if manifest.is_file() and plugin_py.is_file():
                found.append(manifest.resolve())
        return found

    def load_plugin(self, manifest_path: Path) -> PluginEntry:
        """Load a single plugin from its manifest path.

        Raises ``PluginLoadError`` on a malformed manifest or a failing
        entry point. On success the plugin and its tools are registered
        against the registry and the :class:`PluginEntry` is returned.
        """

        manifest_path = Path(manifest_path).resolve()
        with self._lock:
            manifest = self._read_manifest(manifest_path)
            self._validate_manifest(manifest)
            plugin_dir = manifest_path.parent
            module = self._import_module(plugin_dir, manifest["name"])
            entry_fn = self._resolve_entry_point(module, manifest["entry_point"])

            plugin_entry = PluginEntry(
                name=manifest["name"],
                version=manifest["version"],
                description=manifest["description"],
                entry_point=manifest["entry_point"],
                manifest_path=str(manifest_path),
                tools=list(manifest["tools"]),
            )
            self._registry.unregister_plugin(plugin_entry.name)
            self._registry.register_plugin(plugin_entry)
            entry_fn(self._registry, manifest)

            self._loaded_modules[plugin_entry.name] = module
            return plugin_entry

    def load_all(self) -> list[PluginEntry]:
        """Discover and load every plugin under plugins_dir."""

        loaded: list[PluginEntry] = []
        for manifest_path in self.discover_plugins():
            try:
                loaded.append(self.load_plugin(manifest_path))
            except PluginLoadError as exc:
                logger.warning("Skipping plugin %s: %s", manifest_path, exc)
        return loaded

    def reload_plugins(self) -> list[PluginEntry]:
        """Hot-reload: clear the registry and re-import every plugin.

        Modules are forcibly re-imported (a fresh module object is created
        each time) so changed source files take effect without a sidecar
        restart.
        """

        with self._lock:
            for name in list(self._loaded_modules):
                mod_name = self._module_name(name)
                sys.modules.pop(mod_name, None)
            self._loaded_modules.clear()
            self._registry.clear()
            return self.load_all()

    def _read_manifest(self, manifest_path: Path) -> dict[str, Any]:
        try:
            with open(manifest_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise PluginLoadError(f"cannot read manifest: {exc}") from exc
        if not isinstance(data, dict):
            raise PluginLoadError("manifest root must be a JSON object")
        return data

    def _validate_manifest(self, manifest: dict[str, Any]) -> None:
        missing = [k for k in REQUIRED_MANIFEST_KEYS if k not in manifest]
        if missing:
            raise PluginLoadError(f"manifest missing keys: {', '.join(missing)}")
        if not isinstance(manifest["name"], str) or not manifest["name"]:
            raise PluginLoadError("manifest 'name' must be a non-empty string")
        if not isinstance(manifest["tools"], list):
            raise PluginLoadError("manifest 'tools' must be a list")
        for i, tool in enumerate(manifest["tools"]):
            if not isinstance(tool, dict) or "name" not in tool:
                raise PluginLoadError(f"tools[{i}] must be an object with a 'name'")

    def _module_name(self, plugin_name: str) -> str:
        return f"ganesh_plugin_{plugin_name}"

    def _import_module(self, plugin_dir: Path, plugin_name: str) -> Any:
        plugin_py = plugin_dir / PLUGIN_FILENAME
        mod_name = self._module_name(plugin_name)
        sys.modules.pop(mod_name, None)
        spec = importlib.util.spec_from_file_location(mod_name, str(plugin_py))
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"cannot create import spec for {plugin_py}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            sys.modules.pop(mod_name, None)
            raise PluginLoadError(f"plugin module exec failed: {exc}") from exc
        return module

    def _resolve_entry_point(self, module: Any, entry_point: str) -> Any:
        fn = getattr(module, entry_point, None)
        if not callable(fn):
            raise PluginLoadError(
                f"entry point '{entry_point}' not found or not callable"
            )
        return fn


class PluginLoadError(Exception):
    """Raised when a plugin manifest or module cannot be loaded."""


_loader: Optional[PluginLoader] = None
_loader_lock = threading.Lock()


def get_loader() -> PluginLoader:
    """Return the process-wide :class:`PluginLoader`, creating it lazily."""

    global _loader
    with _loader_lock:
        if _loader is None:
            _loader = PluginLoader()
        return _loader


def reset_loader() -> None:
    """Drop the singleton (tests). Also clears the registry."""

    global _loader
    with _loader_lock:
        if _loader is not None:
            _loader.registry.clear()
        _loader = None


def set_loader(loader: PluginLoader) -> None:
    """Inject a custom loader (tests)."""

    global _loader
    with _loader_lock:
        _loader = loader
