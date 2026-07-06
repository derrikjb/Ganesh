"""FastAPI router for memory CRUD endpoints.

Endpoints
---------
POST   /api/memory          — store a memory (scoped to active profile)
GET    /api/memory          — retrieve memories (semantic search via ?query=)
GET    /api/memory/list     — list all memories for the active profile
PUT    /api/memory/{id}     — update a memory
DELETE /api/memory/{id}     — delete a memory
GET    /api/memory/integrity  — probe LanceDB integrity (Task 40)
POST   /api/memory/repair     — re-index from JSON backup (Task 40)
POST   /api/memory/reset      — archive corrupted DB, start fresh (Task 40)

All operations are scoped by ``profile_id``. The active profile is read from
the :class:`ProfileManager` singleton; callers may override it with the
``profile_id`` query parameter.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ganesh_backend.embeddings import create_default_embedder
from ganesh_backend.services.memory import MemoryService

router = APIRouter(prefix="/api/memory", tags=["memory"])


def _data_dir() -> Path:
    env_dir = os.environ.get("GANESH_DATA_DIR")
    if env_dir:
        path = Path(env_dir)
    else:
        path = Path.home() / ".ganesh" / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


_service: Optional[MemoryService] = None


def get_memory_service() -> MemoryService:
    global _service
    if _service is None:
        embedder = create_default_embedder()
        _service = MemoryService(
            db_path=str(_data_dir() / "lancedb"),
            embedder=embedder,
        )
    return _service


def reset_memory_service() -> None:
    global _service
    _service = None


def set_memory_service(svc: MemoryService) -> None:
    global _service
    _service = svc


def _resolve_profile_id(explicit: Optional[str]) -> Optional[str]:
    """Return the profile_id to scope by.

    If ``explicit`` is provided, use it. Otherwise fall back to the active
    profile from the profile manager. Returns ``None`` if no profile manager
    is available (e.g. when the memory router is used standalone in tests).
    """
    if explicit is not None:
        return explicit
    try:
        from ganesh_backend.services.profiles import get_profile_manager
        mgr = get_profile_manager()
        return mgr.get_active_profile_id()
    except Exception:
        return None


class StoreMemoryRequest(BaseModel):
    content: str = Field(..., min_length=1)
    metadata: Optional[dict[str, Any]] = None


class UpdateMemoryRequest(BaseModel):
    content: str = Field(..., min_length=1)
    metadata: Optional[dict[str, Any]] = None


class MemoryResponse(BaseModel):
    id: str
    content: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str


class RetrieveResponse(BaseModel):
    query: str
    results: list[MemoryResponse]


class ListResponse(BaseModel):
    memories: list[MemoryResponse]


class IntegrityResponse(BaseModel):
    healthy: bool
    schema_version_expected: int
    schema_version_found: Optional[int] = None
    error: Optional[str] = None


class RepairResponse(BaseModel):
    restored: int
    backup_path: Optional[str] = None


class ResetResponse(BaseModel):
    archived: bool
    message: str


@router.post("", response_model=MemoryResponse, status_code=201)
async def store_memory(
    req: StoreMemoryRequest,
    profile_id: Optional[str] = Query(None),
) -> MemoryResponse:
    service = get_memory_service()
    pid = _resolve_profile_id(profile_id)
    record = service.store_memory(
        content=req.content, metadata=req.metadata, profile_id=pid
    )
    return MemoryResponse(**record.to_dict())


@router.get("", response_model=RetrieveResponse)
async def retrieve_memories(
    query: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=100),
    profile_id: Optional[str] = Query(None),
) -> RetrieveResponse:
    service = get_memory_service()
    pid = _resolve_profile_id(profile_id)
    records = service.retrieve_memories(query=query, limit=limit, profile_id=pid)
    return RetrieveResponse(
        query=query,
        results=[MemoryResponse(**r.to_dict()) for r in records],
    )


@router.get("/list", response_model=ListResponse)
async def list_memories(
    profile_id: Optional[str] = Query(None),
) -> ListResponse:
    service = get_memory_service()
    pid = _resolve_profile_id(profile_id)
    records = service.list_memories(profile_id=pid)
    return ListResponse(memories=[MemoryResponse(**r.to_dict()) for r in records])


@router.get("/integrity", response_model=IntegrityResponse)
async def check_integrity() -> IntegrityResponse:
    service = get_memory_service()
    report = service.check_integrity()
    return IntegrityResponse(**report)


@router.get("/health", response_model=IntegrityResponse)
async def memory_health() -> IntegrityResponse:
    service = get_memory_service()
    report = service.check_integrity()
    return IntegrityResponse(**report)


@router.post("/repair", response_model=RepairResponse)
async def repair_memory() -> RepairResponse:
    service = get_memory_service()
    backup_path = service._backup_path()
    if backup_path is None or not backup_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No backup file found. Cannot repair without a backup.",
        )
    try:
        restored = service.repair_from_backup(backup_path)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RepairResponse(restored=restored, backup_path=str(backup_path))


@router.post("/reset", response_model=ResetResponse)
async def reset_memory() -> ResetResponse:
    service = get_memory_service()
    archived = service.reset(archive=True)
    return ResetResponse(
        archived=archived,
        message="Memory database archived and reset to a fresh state.",
    )


@router.put("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: str,
    req: UpdateMemoryRequest,
    profile_id: Optional[str] = Query(None),
) -> MemoryResponse:
    service = get_memory_service()
    pid = _resolve_profile_id(profile_id)
    record = service.update_memory(
        memory_id, content=req.content, metadata=req.metadata, profile_id=pid
    )
    if record is None:
        raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found")
    return MemoryResponse(**record.to_dict())


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: str,
    profile_id: Optional[str] = Query(None),
) -> None:
    service = get_memory_service()
    pid = _resolve_profile_id(profile_id)
    deleted = service.delete_memory(memory_id, profile_id=pid)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found")
