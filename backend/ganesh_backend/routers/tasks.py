"""FastAPI router for the async task manager.

Endpoints
---------
POST   /api/tasks              — start a background task
GET    /api/tasks              — list all tasks
GET    /api/tasks/{id}         — get a single task's status
POST   /api/tasks/{id}/cancel  — cancel a running task
GET    /api/tasks/{id}/stream  — SSE stream of progress updates
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ganesh_backend.services.task_manager import (
    TaskManager,
    get_task_manager,
    reset_task_manager,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _manager() -> TaskManager:
    return get_task_manager()


class StartTaskRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    task_type: str = Field(..., min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)


class TaskResponse(BaseModel):
    id: str
    goal: str
    status: str
    current_action: Optional[str] = None
    result: Optional[Any] = None
    started_at: str
    completed_at: Optional[str] = None
    task_type: str


class ListTasksResponse(BaseModel):
    tasks: list[TaskResponse]


class StartTaskResponse(BaseModel):
    id: str
    status: str


class CancelTaskResponse(BaseModel):
    id: str
    cancelled: bool


@router.post("", response_model=StartTaskResponse, status_code=201)
async def start_task(req: StartTaskRequest) -> StartTaskResponse:
    mgr = _manager()
    try:
        task_id = await mgr.start_task(
            goal=req.goal, task_type=req.task_type, input=req.input
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StartTaskResponse(id=task_id, status="pending")


@router.get("", response_model=ListTasksResponse)
async def list_tasks() -> ListTasksResponse:
    mgr = _manager()
    rows = mgr.list_tasks()
    return ListTasksResponse(tasks=[TaskResponse(**r) for r in rows])


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str) -> TaskResponse:
    mgr = _manager()
    row = mgr.get_task(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return TaskResponse(**row)


@router.post("/{task_id}/cancel", response_model=CancelTaskResponse)
async def cancel_task(task_id: str) -> CancelTaskResponse:
    mgr = _manager()
    cancelled = await mgr.cancel_task(task_id)
    if not cancelled:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found or already terminal",
        )
    return CancelTaskResponse(id=task_id, cancelled=True)


@router.get("/{task_id}/stream")
async def task_stream(task_id: str) -> StreamingResponse:
    mgr = _manager()
    if mgr.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    async def event_source() -> AsyncIterator[bytes]:
        async for update in mgr.get_task_stream(task_id):
            yield _sse_chunk(update).encode()
        # Final flush with the terminal DB state so clients always see the
        # settled status even if the in-memory stream ended abruptly.
        final = mgr.get_task(task_id)
        if final is not None:
            yield _sse_chunk(
                {
                    "status": final["status"],
                    "action": final["current_action"],
                    "result": final.get("result"),
                },
                event="done",
            ).encode()

    return StreamingResponse(event_source(), media_type="text/event-stream")


def _sse_chunk(data: dict[str, Any], event: Optional[str] = None) -> str:
    payload = json.dumps(data)
    if event:
        return f"event: {event}\ndata: {payload}\n\n"
    return f"data: {payload}\n\n"


def reset_router_singleton() -> None:
    """Clear the process-wide task manager (used by tests)."""
    reset_task_manager()
