"""FastAPI router for proactive pattern suggestions (Task 35).

Endpoints
---------
POST   /api/patterns/record          — record a behavior occurrence
GET    /api/patterns                  — list active patterns
GET    /api/patterns/suggestible       — list patterns eligible for suggestion
POST   /api/patterns/suggest          — generate a suggestion for a context
POST   /api/patterns/{id}/accept      — accept a suggestion (confidence +0.1)
POST   /api/patterns/{id}/decline      — decline a suggestion (confidence -0.2)
POST   /api/patterns/{id}/disable      — disable a pattern (archived)

All operations are scoped by ``profile_id`` (resolved from the active profile
when not explicitly provided), mirroring the memory router.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ganesh_backend.services.patterns import (
    get_pattern_service,
    reset_pattern_service,
    set_pattern_service,
)
from ganesh_backend.services.suggestion_engine import (
    get_suggestion_engine,
    reset_suggestion_engine,
    set_suggestion_engine,
)


router = APIRouter(prefix="/api/patterns", tags=["patterns"])


def _resolve_profile_id(explicit: Optional[str]) -> Optional[str]:
    if explicit is not None:
        return explicit
    try:
        from ganesh_backend.services.profiles import get_profile_manager

        return get_profile_manager().get_active_profile_id()
    except Exception:
        return None


class RecordBehaviorRequest(BaseModel):
    trigger: str = Field(..., min_length=1)
    followup: str = Field(..., min_length=1)


class SuggestRequest(BaseModel):
    context: str = Field(..., min_length=1)
    limit: int = Field(3, ge=1, le=10)


class PatternResponse(BaseModel):
    id: str
    trigger: str
    followup: str
    occurrences: int
    confidence: float
    status: str
    profile_id: Optional[str] = None
    created_at: str
    updated_at: str
    last_suggested_at: Optional[str] = None


class ListResponse(BaseModel):
    patterns: list[PatternResponse]


class SuggestionResponse(BaseModel):
    suggestion: Optional[dict[str, Any]] = None
    note: str = ""


@router.post("/record", response_model=PatternResponse, status_code=201)
async def record_behavior(
    req: RecordBehaviorRequest,
    profile_id: Optional[str] = Query(None),
) -> PatternResponse:
    service = get_pattern_service()
    pid = _resolve_profile_id(profile_id)
    try:
        pattern = service.record_behavior(
            trigger=req.trigger, followup=req.followup, profile_id=pid
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PatternResponse(**pattern.to_dict())


@router.get("", response_model=ListResponse)
async def list_patterns(
    include_archived: bool = Query(False),
    profile_id: Optional[str] = Query(None),
) -> ListResponse:
    service = get_pattern_service()
    pid = _resolve_profile_id(profile_id)
    patterns = service.list_patterns(
        profile_id=pid, include_archived=include_archived
    )
    return ListResponse(
        patterns=[PatternResponse(**p.to_dict()) for p in patterns]
    )


@router.get("/suggestible", response_model=ListResponse)
async def suggestible_patterns(
    profile_id: Optional[str] = Query(None),
) -> ListResponse:
    service = get_pattern_service()
    pid = _resolve_profile_id(profile_id)
    patterns = service.get_suggestible_patterns(profile_id=pid)
    return ListResponse(
        patterns=[PatternResponse(**p.to_dict()) for p in patterns]
    )


@router.post("/suggest", response_model=SuggestionResponse)
async def suggest(
    req: SuggestRequest,
    profile_id: Optional[str] = Query(None),
) -> SuggestionResponse:
    engine = get_suggestion_engine()
    pid = _resolve_profile_id(profile_id)
    suggestions = engine.generate_suggestions(
        context=req.context, profile_id=pid, limit=req.limit
    )
    note = engine.build_system_note(suggestions)
    if not suggestions:
        return SuggestionResponse(suggestion=None, note="")
    return SuggestionResponse(
        suggestion=suggestions[0].to_dict(), note=note
    )


@router.post("/{pattern_id}/accept", response_model=PatternResponse)
async def accept_pattern(
    pattern_id: str,
    profile_id: Optional[str] = Query(None),
) -> PatternResponse:
    service = get_pattern_service()
    pid = _resolve_profile_id(profile_id)
    pattern = service.accept_pattern(pattern_id, profile_id=pid)
    if pattern is None:
        raise HTTPException(
            status_code=404, detail=f"Pattern {pattern_id} not found"
        )
    return PatternResponse(**pattern.to_dict())


@router.post("/{pattern_id}/decline", response_model=PatternResponse)
async def decline_pattern(
    pattern_id: str,
    profile_id: Optional[str] = Query(None),
) -> PatternResponse:
    service = get_pattern_service()
    pid = _resolve_profile_id(profile_id)
    pattern = service.decline_pattern(pattern_id, profile_id=pid)
    if pattern is None:
        raise HTTPException(
            status_code=404, detail=f"Pattern {pattern_id} not found"
        )
    return PatternResponse(**pattern.to_dict())


@router.post("/{pattern_id}/disable", response_model=PatternResponse)
async def disable_pattern(
    pattern_id: str,
    profile_id: Optional[str] = Query(None),
) -> PatternResponse:
    service = get_pattern_service()
    pid = _resolve_profile_id(profile_id)
    pattern = service.disable_pattern(pattern_id, profile_id=pid)
    if pattern is None:
        raise HTTPException(
            status_code=404, detail=f"Pattern {pattern_id} not found"
        )
    return PatternResponse(**pattern.to_dict())


__all__ = [
    "router",
    "get_pattern_service",
    "set_pattern_service",
    "reset_pattern_service",
    "get_suggestion_engine",
    "set_suggestion_engine",
    "reset_suggestion_engine",
]
