"""Plugin registry: stores loaded plugins and their tool callables.

The registry is the single source of truth for "what tools are available"
across all loaded plugins. The :class:`PluginLoader` populates it; the
``/api/plugins`` router reads from it.

A *tool* is a named callable plus a JSON-schema-ish parameter dict::

    {
        "name": "take_note",
        "description": "Save a short note to disk",
        "parameters": {"text": {"type": "string", "required": True}}
    }

The registry is thread-safe (an RLock guards mutation) and intentionally
process-wide — there is one registry per sidecar instance.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


ToolFn = Callable[..., Any]


@dataclass
class ToolEntry:
    """A registered tool: its callable, schema, and owning plugin."""

    plugin_name: str
    tool_name: str
    fn: ToolFn
    schema: dict[str, Any] = field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        """``plugin.tool`` — globally unique across plugins."""

        return f"{self.plugin_name}.{self.tool_name}"


@dataclass
class PluginEntry:
    """A loaded plugin: its manifest metadata and registered tools."""

    name: str
    version: str
    description: str
    entry_point: str
    manifest_path: str
    tools: list[dict[str, Any]] = field(default_factory=list)


class PluginRegistry:
    """Thread-safe registry of loaded plugins and their tools."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._plugins: dict[str, PluginEntry] = {}
        self._tools: dict[str, ToolEntry] = {}

    def register_plugin(self, plugin: PluginEntry) -> None:
        """Insert or replace a plugin entry (called by the loader)."""

        with self._lock:
            self._plugins[plugin.name] = plugin

    def register_tool(
        self,
        plugin_name: str,
        tool_name: str,
        fn: ToolFn,
        schema: dict[str, Any],
    ) -> None:
        """Register a tool under ``plugin_name.tool_name``.

        Re-registering the same qualified name replaces the previous entry
        (used by hot-reload).
        """

        entry = ToolEntry(
            plugin_name=plugin_name,
            tool_name=tool_name,
            fn=fn,
            schema=schema,
        )
        with self._lock:
            self._tools[entry.qualified_name] = entry

    def unregister_plugin(self, plugin_name: str) -> None:
        """Remove a plugin and all of its tools (used by hot-reload)."""

        with self._lock:
            self._plugins.pop(plugin_name, None)
            doomed = [
                qn for qn, te in self._tools.items() if te.plugin_name == plugin_name
            ]
            for qn in doomed:
                del self._tools[qn]

    def clear(self) -> None:
        """Wipe the registry (used by tests and full reloads)."""

        with self._lock:
            self._plugins.clear()
            self._tools.clear()

    def get_plugin(self, plugin_name: str) -> Optional[PluginEntry]:
        with self._lock:
            return self._plugins.get(plugin_name)

    def list_plugins(self) -> list[PluginEntry]:
        with self._lock:
            return list(self._plugins.values())

    def get_tool(self, tool_name: str) -> Optional[ToolEntry]:
        """Look up a tool by qualified name ``plugin.tool`` or bare name.

        Bare names are matched only when unambiguous across plugins.
        """

        with self._lock:
            if "." in tool_name:
                return self._tools.get(tool_name)
            matches = [te for te in self._tools.values() if te.tool_name == tool_name]
            if len(matches) == 1:
                return matches[0]
            return None

    def list_tools(self) -> list[ToolEntry]:
        with self._lock:
            return list(self._tools.values())


_registry: Optional[PluginRegistry] = None
_registry_lock = threading.Lock()


def get_registry() -> PluginRegistry:
    """Return the process-wide :class:`PluginRegistry`, creating it lazily."""

    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = PluginRegistry()
        return _registry


def reset_registry() -> None:
    """Drop the singleton (tests). Also clears any registered tools."""

    global _registry
    with _registry_lock:
        if _registry is not None:
            _registry.clear()
        _registry = None


def set_registry(registry: PluginRegistry) -> None:
    """Inject a custom registry (tests)."""

    global _registry
    with _registry_lock:
        _registry = registry
