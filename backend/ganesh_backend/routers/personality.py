"""Personality router: trait matrix CRUD + context-based shifting."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ganesh_backend.services.personality import (
    TRAIT_BOUNDS,
    engine as default_engine,
    PersonalityEngine,
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
    }


@router.get("/traits")
async def get_traits() -> dict[str, Any]:
    return _traits_payload(default_engine)


@router.put("/traits")
async def update_traits(update: TraitUpdate) -> dict[str, Any]:
    try:
        default_engine.update_traits(update.traits)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _traits_payload(default_engine)


@router.post("/shift")
async def shift_traits(req: ShiftRequest) -> dict[str, Any]:
    default_engine.shift_traits(req.context)
    return _traits_payload(default_engine)


@router.post("/lock/{trait}")
async def lock_trait(trait: str) -> dict[str, Any]:
    if trait not in TRAIT_BOUNDS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown trait: {trait!r}. Known: {sorted(TRAIT_BOUNDS)}",
        )
    default_engine.lock_trait(trait)
    return _traits_payload(default_engine)


@router.post("/unlock/{trait}")
async def unlock_trait(trait: str) -> dict[str, Any]:
    if trait not in TRAIT_BOUNDS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown trait: {trait!r}. Known: {sorted(TRAIT_BOUNDS)}",
        )
    default_engine.unlock_trait(trait)
    return _traits_payload(default_engine)


@router.post("/reset")
async def reset_traits() -> dict[str, Any]:
    default_engine.reset_traits()
    return _traits_payload(default_engine)


@router.get("/system-prompt")
async def get_system_prompt() -> dict[str, str]:
    return {"prompt": default_engine.get_system_prompt()}
