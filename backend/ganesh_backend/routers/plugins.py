"""FastAPI router for the dynamic plugin system.

Endpoints
---------
GET   /api/plugins                                  — list loaded plugins
GET   /api/plugins/tools                            — list all registered tools
POST  /api/plugins/{plugin_name}/{tool_name}/invoke — invoke a plugin tool
POST  /api/plugins/reload                           — hot-reload all plugins
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ganesh_backend.services.plugin_loader import (
    PluginLoadError,
    get_loader,
    reset_loader,
    set_loader,
    PluginLoader,
)
from ganesh_backend.services.plugin_registry import (
    PluginRegistry,
    get_registry,
    reset_registry,
    set_registry,
)

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


def _loader() -> PluginLoader:
    return get_loader()


def _registry() -> PluginRegistry:
    return get_registry()


class PluginSummary(BaseModel):
    name: str
    version: str
    description: str
    entry_point: str
    manifest_path: str
    tools: list[dict[str, Any]]


class ListPluginsResponse(BaseModel):
    plugins: list[PluginSummary]


class ToolSummary(BaseModel):
    plugin_name: str
    tool_name: str
    qualified_name: str
    tool_schema: dict[str, Any] = Field(default_factory=dict)


class ListToolsResponse(BaseModel):
    tools: list[ToolSummary]


class InvokeToolRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)


class InvokeToolResponse(BaseModel):
    plugin: str
    tool: str
    result: Any


class ReloadResponse(BaseModel):
    reloaded: list[str]


@router.get("", response_model=ListPluginsResponse)
async def list_plugins() -> ListPluginsResponse:
    reg = _registry()
    plugins = [
        PluginSummary(
            name=p.name,
            version=p.version,
            description=p.description,
            entry_point=p.entry_point,
            manifest_path=p.manifest_path,
            tools=list(p.tools),
        )
        for p in reg.list_plugins()
    ]
    return ListPluginsResponse(plugins=plugins)


@router.get("/tools", response_model=ListToolsResponse)
async def list_tools() -> ListToolsResponse:
    reg = _registry()
    tools = [
        ToolSummary(
            plugin_name=t.plugin_name,
            tool_name=t.tool_name,
            qualified_name=t.qualified_name,
            tool_schema=dict(t.schema),
        )
        for t in reg.list_tools()
    ]
    return ListToolsResponse(tools=tools)


@router.post(
    "/{plugin_name}/{tool_name}/invoke",
    response_model=InvokeToolResponse,
)
async def invoke_tool(
    plugin_name: str, tool_name: str, req: InvokeToolRequest
) -> InvokeToolResponse:
    reg = _registry()
    qualified = f"{plugin_name}.{tool_name}"
    entry = reg.get_tool(qualified)
    if entry is None or entry.plugin_name != plugin_name:
        raise HTTPException(
            status_code=404,
            detail=f"tool {qualified} not found",
        )
    try:
        result = entry.fn(**req.parameters)
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=f"bad parameters: {exc}") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"tool execution failed: {exc}"
        ) from exc
    return InvokeToolResponse(plugin=plugin_name, tool=tool_name, result=result)


@router.post("/reload", response_model=ReloadResponse)
async def reload_plugins() -> ReloadResponse:
    loader = _loader()
    try:
        loaded = loader.reload_plugins()
    except PluginLoadError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ReloadResponse(reloaded=[p.name for p in loaded])


def reset_router_singletons() -> None:
    """Clear process-wide loader + registry (used by tests)."""

    reset_loader()
    reset_registry()


def set_router_singletons(
    loader: PluginLoader, registry: PluginRegistry
) -> None:
    """Inject custom loader + registry (used by tests)."""

    set_loader(loader)
    set_registry(registry)
