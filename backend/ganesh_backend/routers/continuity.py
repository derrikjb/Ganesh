"""FastAPI router for session continuity endpoints.

Endpoints (under ``/api/continuity``):
    POST /api/continuity/start    — start a session for the active profile
    POST /api/continuity/end      — end the current session
    GET  /api/continuity/welcome  — get welcome-back message (or null)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ganesh_backend.services.continuity import (
    ContinuityService,
    get_continuity_service,
    reset_continuity_service,
    set_continuity_service,
)
from ganesh_backend.services.profiles import get_profile_manager

router = APIRouter(prefix="/api/continuity", tags=["continuity"])


class SessionResponse(BaseModel):
    id: str
    profile_id: str
    started_at: float
    ended_at: Optional[float] = None
    last_topic: Optional[str] = None
    last_task_id: Optional[str] = None


class EndSessionRequest(BaseModel):
    session_id: Optional[str] = None
    last_topic: Optional[str] = None
    last_task_id: Optional[str] = None


def _svc() -> ContinuityService:
    return get_continuity_service()


def _active_profile_id() -> str:
    pid = get_profile_manager().get_active_profile_id()
    if pid is None:
        raise HTTPException(status_code=404, detail="No active profile")
    return pid


def reset_router_singleton() -> None:
    reset_continuity_service()


def set_router_singleton(svc: ContinuityService) -> None:
    set_continuity_service(svc)


@router.post("/start", response_model=SessionResponse, status_code=201)
async def start_session() -> SessionResponse:
    profile_id = _active_profile_id()
    session = _svc().start_session(profile_id)
    return SessionResponse(**session.to_dict())


@router.post("/end", response_model=SessionResponse)
async def end_session(req: EndSessionRequest) -> SessionResponse:
    svc = _svc()
    session_id = req.session_id
    if session_id is None:
        profile_id = _active_profile_id()
        open_session = svc.get_open_session(profile_id)
        if open_session is None:
            raise HTTPException(
                status_code=404, detail="No open session for active profile"
            )
        session_id = open_session.id
    session = svc.end_session(
        session_id=session_id,
        last_topic=req.last_topic,
        last_task_id=req.last_task_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return SessionResponse(**session.to_dict())


@router.get("/welcome")
async def welcome() -> dict[str, object]:
    profile_id = _active_profile_id()
    payload = _svc().generate_welcome_back(profile_id)
    if payload is None:
        return {"message": None}
    return payload
