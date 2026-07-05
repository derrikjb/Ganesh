"""FastAPI router for the sub-agent orchestrator.

Endpoints
---------
POST   /api/agents/spawn        — spawn a sub-agent
GET    /api/agents              — list active sub-agents
GET    /api/agents/{id}/status  — non-blocking status summary
GET    /api/agents/{id}/result  — fetch result when complete
POST   /api/agents/{id}/cancel  — cancel a running sub-agent
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ganesh_backend.services.orchestrator import (
    Orchestrator,
    get_orchestrator,
    reset_orchestrator,
)

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _orchestrator() -> Orchestrator:
    return get_orchestrator()


class SpawnSubAgentRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    task_type: str = Field(..., min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)


class SpawnSubAgentResponse(BaseModel):
    task_id: str
    status: str


class SubAgentStatusResponse(BaseModel):
    task_id: str
    goal: str
    status: str
    current_action: str = ""
    task_type: str = ""
    started_at: str = ""
    completed_at: Optional[str] = None


class SubAgentResultResponse(BaseModel):
    task_id: str
    goal: str
    status: str
    result: Optional[Any] = None
    completed_at: Optional[str] = None


class ListSubAgentsResponse(BaseModel):
    agents: list[SubAgentStatusResponse]


class CancelSubAgentResponse(BaseModel):
    task_id: str
    cancelled: bool


@router.post("/spawn", response_model=SpawnSubAgentResponse, status_code=201)
async def spawn_sub_agent(req: SpawnSubAgentRequest) -> SpawnSubAgentResponse:
    orch = _orchestrator()
    task_id = await orch.spawn_sub_agent(
        goal=req.goal,
        task_type=req.task_type,
        input=req.input,
        tools=req.tools,
    )
    return SpawnSubAgentResponse(task_id=task_id, status="pending")


@router.get("", response_model=ListSubAgentsResponse)
async def list_active_sub_agents() -> ListSubAgentsResponse:
    orch = _orchestrator()
    rows = orch.list_active_sub_agents()
    return ListSubAgentsResponse(
        agents=[SubAgentStatusResponse(**r) for r in rows]
    )


@router.get("/{task_id}/status", response_model=SubAgentStatusResponse)
async def get_sub_agent_status(task_id: str) -> SubAgentStatusResponse:
    orch = _orchestrator()
    row = orch.query_sub_agent_status(task_id)
    if row is None:
        raise HTTPException(
            status_code=404, detail=f"Sub-agent {task_id} not found"
        )
    return SubAgentStatusResponse(**row)


@router.get("/{task_id}/result", response_model=SubAgentResultResponse)
async def get_sub_agent_result(task_id: str) -> SubAgentResultResponse:
    orch = _orchestrator()
    row = orch.get_sub_agent_result(task_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Sub-agent {task_id} not found or not complete",
        )
    return SubAgentResultResponse(**row)


@router.post("/{task_id}/cancel", response_model=CancelSubAgentResponse)
async def cancel_sub_agent(task_id: str) -> CancelSubAgentResponse:
    orch = _orchestrator()
    cancelled = await orch.cancel_sub_agent(task_id)
    if not cancelled:
        raise HTTPException(
            status_code=404,
            detail=f"Sub-agent {task_id} not found or already terminal",
        )
    return CancelSubAgentResponse(task_id=task_id, cancelled=True)


def reset_router_singleton() -> None:
    """Clear the process-wide orchestrator (used by tests)."""
    reset_orchestrator()
