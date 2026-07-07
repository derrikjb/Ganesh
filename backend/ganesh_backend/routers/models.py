"""FastAPI router for first-run model download management.

Endpoints
---------
GET    /api/models/status    — returns which models are missing/present
POST   /api/models/download   — starts a download (async background task)
GET    /api/models/progress   — SSE stream of download progress
POST   /api/models/pause      — pauses a download
POST   /api/models/resume     — resumes a paused download
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from ganesh_backend.services.model_manager import (
    REQUIRED_MODELS,
    DiskFullError,
    ModelManager,
    get_model_manager,
    reset_model_manager,
)

router = APIRouter(prefix="/api/models", tags=["models"])


class DownloadRequest(BaseModel):
    name: str


class ModelStatus(BaseModel):
    name: str
    description: str
    present: bool
    size: int = 0


class StatusResponse(BaseModel):
    models: list[ModelStatus]
    all_present: bool


class PauseResumeResponse(BaseModel):
    name: str
    status: str


class DiskSpaceResponse(BaseModel):
    free_bytes: int
    name: str
    required_bytes: int
    has_space: bool


def _manager() -> ModelManager:
    return get_model_manager()


@router.get("/status", response_model=StatusResponse)
async def status() -> StatusResponse:
    mgr = _manager()
    presence = mgr.check_models()
    models = [
        ModelStatus(
            name=name,
            description=spec.description,
            present=presence.get(name, False),
            size=spec.size,
        )
        for name, spec in REQUIRED_MODELS.items()
    ]
    return StatusResponse(models=models, all_present=all(m.present for m in models))


@router.get("/disk-space")
async def disk_space() -> dict[str, object]:
    return _manager().check_disk_space()


@router.get("/disk-space/{name}", response_model=DiskSpaceResponse)
async def disk_space_for_model(name: str) -> DiskSpaceResponse:
    if name not in REQUIRED_MODELS:
        raise HTTPException(status_code=404, detail=f"Unknown model: {name}")
    mgr = _manager()
    has_space, free, required = mgr.has_space_for(name)
    return DiskSpaceResponse(
        free_bytes=free,
        name=name,
        required_bytes=required,
        has_space=has_space,
    )


@router.post("/download")
async def download(req: DownloadRequest) -> dict[str, str]:
    if req.name not in REQUIRED_MODELS:
        raise HTTPException(status_code=404, detail=f"Unknown model: {req.name}")
    mgr = _manager()

    async def _run() -> None:
        try:
            await mgr.download_model(req.name)
        except DiskFullError:
            pass
        except Exception:
            pass

    asyncio.create_task(_run())
    return {"name": req.name, "status": "started"}


@router.get("/progress")
async def progress_stream() -> StreamingResponse:
    async def stream() -> AsyncIterator[bytes]:
        mgr = _manager()
        last_snapshot: str = ""
        idle_ticks = 0
        while True:
            snapshot = mgr.get_progress_snapshot()
            payload = json.dumps({"models": snapshot})
            if payload != last_snapshot:
                yield f"data: {payload}\n\n".encode()
                last_snapshot = payload
                idle_ticks = 0
            else:
                idle_ticks += 1
            statuses = [p.get("status") for p in snapshot.values()]
            if statuses and all(s == "completed" for s in statuses):
                yield f"event: done\ndata: {payload}\n\n".encode()
                return
            if idle_ticks > 600:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/pause", response_model=PauseResumeResponse)
async def pause(req: DownloadRequest) -> PauseResumeResponse:
    if req.name not in REQUIRED_MODELS:
        raise HTTPException(status_code=404, detail=f"Unknown model: {req.name}")
    _manager().pause_download(req.name)
    return PauseResumeResponse(name=req.name, status="paused")


@router.post("/resume", response_model=PauseResumeResponse)
async def resume(req: DownloadRequest) -> PauseResumeResponse:
    if req.name not in REQUIRED_MODELS:
        raise HTTPException(status_code=404, detail=f"Unknown model: {req.name}")
    _manager().resume_download(req.name)
    return PauseResumeResponse(name=req.name, status="downloading")


def _reset() -> None:
    reset_model_manager()
