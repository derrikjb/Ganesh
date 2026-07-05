"""FastAPI router for memory CRUD endpoints.

Endpoints
---------
POST   /api/memory          — store a memory
GET    /api/memory          — retrieve memories (semantic search via ?query=)
GET    /api/memory/list     — list all memories
PUT    /api/memory/{id}     — update a memory
DELETE /api/memory/{id}     — delete a memory
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ganesh_backend.embeddings import HashEmbedder, create_default_embedder
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


@router.post("", response_model=MemoryResponse, status_code=201)
async def store_memory(req: StoreMemoryRequest) -> MemoryResponse:
    service = get_memory_service()
    record = service.store_memory(content=req.content, metadata=req.metadata)
    return MemoryResponse(**record.to_dict())


@router.get("", response_model=RetrieveResponse)
async def retrieve_memories(
    query: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=100),
) -> RetrieveResponse:
    service = get_memory_service()
    records = service.retrieve_memories(query=query, limit=limit)
    return RetrieveResponse(
        query=query,
        results=[MemoryResponse(**r.to_dict()) for r in records],
    )


@router.get("/list", response_model=ListResponse)
async def list_memories() -> ListResponse:
    service = get_memory_service()
    records = service.list_memories()
    return ListResponse(memories=[MemoryResponse(**r.to_dict()) for r in records])


@router.put("/{memory_id}", response_model=MemoryResponse)
async def update_memory(memory_id: str, req: UpdateMemoryRequest) -> MemoryResponse:
    service = get_memory_service()
    record = service.update_memory(memory_id, content=req.content, metadata=req.metadata)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found")
    return MemoryResponse(**record.to_dict())


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(memory_id: str) -> None:
    service = get_memory_service()
    deleted = service.delete_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found")
