"""FastAPI router for profile management + shared bridge memory layer.

Profile endpoints (under ``/api/profiles``):
    POST   /api/profiles              — create profile
    GET    /api/profiles              — list profiles
    GET    /api/profiles/active       — get active profile
    GET    /api/profiles/{id}         — get profile
    PUT    /api/profiles/{id}         — update profile
    DELETE /api/profiles/{id}         — delete profile (cascades)
    POST   /api/profiles/{id}/activate — switch active profile

Bridge endpoints (under ``/api/profiles/bridge``):
    POST   /api/profiles/bridge/grant       — grant cross-profile access
    DELETE /api/profiles/bridge/grant/{id}  — revoke grant
    GET    /api/profiles/bridge/query        — semantic query across grants
    GET    /api/profiles/bridge/audit        — list audit log entries
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ganesh_backend.services.bridge import BridgeService, get_bridge_service
from ganesh_backend.services.profiles import (
    ProfileManager,
    get_profile_manager,
    reset_profile_manager,
)

router = APIRouter(prefix="/api/profiles", tags=["profiles"])
bridge_router = APIRouter(prefix="/api/profiles/bridge", tags=["bridge"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class CreateProfileRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    color: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None


class ProfileResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    color: Optional[str] = None
    created_at: str
    updated_at: str


class ListProfilesResponse(BaseModel):
    profiles: list[ProfileResponse]
    active_profile_id: Optional[str] = None


class GrantRequest(BaseModel):
    granting_profile_id: str
    receiving_profile_id: str
    memory_id: str


class GrantResponse(BaseModel):
    id: str
    granting_profile_id: str
    receiving_profile_id: str
    memory_id: str
    created_at: str


class ListGrantsResponse(BaseModel):
    grants: list[GrantResponse]


class BridgeQueryResponse(BaseModel):
    query: str
    receiving_profile_id: str
    granting_profile_id: str
    results: list[dict[str, Any]]


class AuditEntryResponse(BaseModel):
    id: int
    receiving_profile_id: str
    granting_profile_id: str
    query: str
    timestamp: str


class AuditResponse(BaseModel):
    entries: list[AuditEntryResponse]


# ---------------------------------------------------------------------------
# Singleton accessors (with test injection)
# ---------------------------------------------------------------------------


def _profile_mgr() -> ProfileManager:
    return get_profile_manager()


def _bridge_svc() -> BridgeService:
    svc = get_bridge_service()
    # Ensure the bridge service can reach the memory layer.
    try:
        from ganesh_backend.routers.memory import get_memory_service
        svc.set_memory_service(get_memory_service())
    except Exception:
        pass
    return svc


def reset_profile_router_singletons() -> None:
    reset_profile_manager()
    from ganesh_backend.services.bridge import reset_bridge_service
    reset_bridge_service()


# ---------------------------------------------------------------------------
# Profile endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=ProfileResponse, status_code=201)
async def create_profile(req: CreateProfileRequest) -> ProfileResponse:
    try:
        profile = _profile_mgr().create_profile(
            name=req.name, description=req.description, color=req.color
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProfileResponse(**profile.to_dict())


@router.get("", response_model=ListProfilesResponse)
async def list_profiles() -> ListProfilesResponse:
    mgr = _profile_mgr()
    profiles = mgr.list_profiles()
    return ListProfilesResponse(
        profiles=[ProfileResponse(**p.to_dict()) for p in profiles],
        active_profile_id=mgr.get_active_profile_id(),
    )


@router.get("/active", response_model=ProfileResponse)
async def get_active_profile() -> ProfileResponse:
    profile = _profile_mgr().get_active_profile()
    if profile is None:
        raise HTTPException(status_code=404, detail="No active profile")
    return ProfileResponse(**profile.to_dict())


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(profile_id: str) -> ProfileResponse:
    profile = _profile_mgr().get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return ProfileResponse(**profile.to_dict())


@router.put("/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: str, req: UpdateProfileRequest
) -> ProfileResponse:
    try:
        profile = _profile_mgr().update_profile(
            profile_id,
            name=req.name,
            description=req.description,
            color=req.color,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return ProfileResponse(**profile.to_dict())


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(profile_id: str) -> None:
    mgr = _profile_mgr()
    # Cascade: delete the profile's memories + bridge grants BEFORE the row.
    try:
        from ganesh_backend.routers.memory import get_memory_service
        get_memory_service().delete_memories_for_profile(profile_id)
    except Exception:
        pass
    _bridge_svc().revoke_grants_for_profile(profile_id)
    try:
        deleted = mgr.delete_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")


@router.post("/{profile_id}/activate", response_model=ProfileResponse)
async def activate_profile(profile_id: str) -> ProfileResponse:
    profile = _profile_mgr().activate_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found")
    return ProfileResponse(**profile.to_dict())


# ---------------------------------------------------------------------------
# Bridge endpoints
# ---------------------------------------------------------------------------


@bridge_router.post("/grant", response_model=GrantResponse, status_code=201)
async def bridge_grant(req: GrantRequest) -> GrantResponse:
    mgr = _profile_mgr()
    if mgr.get_profile(req.granting_profile_id) is None:
        raise HTTPException(status_code=404, detail="Granting profile not found")
    if mgr.get_profile(req.receiving_profile_id) is None:
        raise HTTPException(status_code=404, detail="Receiving profile not found")
    try:
        grant = _bridge_svc().grant(
            granting_profile_id=req.granting_profile_id,
            receiving_profile_id=req.receiving_profile_id,
            memory_id=req.memory_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GrantResponse(**grant.to_dict())


@bridge_router.delete("/grant/{grant_id}", status_code=204)
async def bridge_revoke(grant_id: str) -> None:
    revoked = _bridge_svc().revoke(grant_id)
    if not revoked:
        raise HTTPException(status_code=404, detail=f"Grant {grant_id} not found")


@bridge_router.get("/grant", response_model=ListGrantsResponse)
async def bridge_list_grants(
    granting_profile_id: Optional[str] = Query(None),
    receiving_profile_id: Optional[str] = Query(None),
) -> ListGrantsResponse:
    grants = _bridge_svc().list_grants(
        granting_profile_id=granting_profile_id,
        receiving_profile_id=receiving_profile_id,
    )
    return ListGrantsResponse(grants=[GrantResponse(**g.to_dict()) for g in grants])


@bridge_router.get("/query", response_model=BridgeQueryResponse)
async def bridge_query(
    receiving_profile_id: str = Query(...),
    granting_profile_id: str = Query(...),
    query: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=100),
) -> BridgeQueryResponse:
    records = _bridge_svc().query(
        receiving_profile_id=receiving_profile_id,
        granting_profile_id=granting_profile_id,
        query=query,
        limit=limit,
    )
    return BridgeQueryResponse(
        query=query,
        receiving_profile_id=receiving_profile_id,
        granting_profile_id=granting_profile_id,
        results=[r.to_dict() for r in records],
    )


@bridge_router.get("/audit", response_model=AuditResponse)
async def bridge_audit(
    receiving_profile_id: Optional[str] = Query(None),
    granting_profile_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> AuditResponse:
    entries = _bridge_svc().list_audit(
        receiving_profile_id=receiving_profile_id,
        granting_profile_id=granting_profile_id,
        limit=limit,
    )
    return AuditResponse(entries=[AuditEntryResponse(**e.to_dict()) for e in entries])


router.include_router(bridge_router)
