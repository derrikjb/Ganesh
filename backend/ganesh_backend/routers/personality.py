"""Personality router: trait matrix CRUD + context-based shifting + persistence."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ganesh_backend.services.personality import (
    TRAIT_BOUNDS,
    PersonalityEngine,
    get_engine,
)


router = APIRouter(prefix="/api/personality", tags=["personality"])


class TraitUpdate(BaseModel):
    traits: dict[str, float] = Field(..., description="Trait name -> new value (clamped).")


class ShiftRequest(BaseModel):
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Conversation context: {message, task_type, ...}",
    )


def _traits_payload(eng: PersonalityEngine) -> dict[str, Any]:
    return {
        "traits": eng.get_traits(),
        "baseline": eng.get_baseline(),
        "locked": eng.locked_traits(),
        "persisted": eng.has_persisted_state(),
    }


@router.get("/traits")
async def get_traits() -> dict[str, Any]:
    return _traits_payload(get_engine())


@router.put("/traits")
async def update_traits(
    update: TraitUpdate,
    persist: bool = Query(True, description="Persist the update to disk."),
) -> dict[str, Any]:
    eng = get_engine()
    try:
        eng.update_traits(update.traits, persist=persist)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _traits_payload(eng)


@router.post("/shift")
async def shift_traits(req: ShiftRequest) -> dict[str, Any]:
    eng = get_engine()
    eng.shift_traits(req.context)
    return _traits_payload(eng)


@router.post("/lock/{trait}")
async def lock_trait(
    trait: str,
    persist: bool = Query(True, description="Persist the lock to disk."),
) -> dict[str, Any]:
    if trait not in TRAIT_BOUNDS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown trait: {trait!r}. Known: {sorted(TRAIT_BOUNDS)}",
        )
    eng = get_engine()
    eng.lock_trait(trait, persist=persist)
    return _traits_payload(eng)


@router.post("/unlock/{trait}")
async def unlock_trait(
    trait: str,
    persist: bool = Query(True, description="Persist the unlock to disk."),
) -> dict[str, Any]:
    if trait not in TRAIT_BOUNDS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown trait: {trait!r}. Known: {sorted(TRAIT_BOUNDS)}",
        )
    eng = get_engine()
    eng.unlock_trait(trait, persist=persist)
    return _traits_payload(eng)


@router.post("/reset")
async def reset_traits() -> dict[str, Any]:
    eng = get_engine()
    eng.reset_traits()
    return _traits_payload(eng)


@router.post("/save")
async def save_traits() -> dict[str, Any]:
    eng = get_engine()
    eng.save()
    return _traits_payload(eng)


@router.post("/load")
async def load_traits() -> dict[str, Any]:
    eng = get_engine()
    eng.load()
    return _traits_payload(eng)


@router.get("/system-prompt")
async def get_system_prompt() -> dict[str, str]:
    return {"prompt": get_engine().get_system_prompt()}
