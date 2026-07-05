"""Emotion router: tone detection + emotion-driven personality shifts.

Exposes the :class:`EmotionAnalyzer` over HTTP. No emotional state is stored
server-side — every request re-analyzes the supplied message window.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ganesh_backend.services.emotion import (
    EmotionAnalyzer,
    get_analyzer,
)
from ganesh_backend.services.personality import get_engine


router = APIRouter(prefix="/api/emotion", tags=["emotion"])


class AnalyzeRequest(BaseModel):
    messages: list[str] = Field(
        ...,
        description="Recent user messages, oldest-first. The trailing "
        "window (default 3) is analyzed.",
    )


class ShiftRequest(BaseModel):
    messages: list[str] = Field(
        ...,
        description="Recent user messages, oldest-first. The trailing "
        "window is analyzed and the resulting trait shifts applied to the "
        "active personality engine.",
    )


def _analyze_payload(
    analyzer: EmotionAnalyzer, messages: list[str]
) -> dict[str, Any]:
    result = analyzer.analyze(messages)
    payload: dict[str, Any] = result.to_dict()
    payload["threshold"] = analyzer._confidence_threshold  # noqa: SLF001
    return payload


@router.get("/supported")
async def supported_emotions() -> dict[str, Any]:
    from ganesh_backend.services.emotion import SUPPORTED_EMOTIONS

    return {"emotions": list(SUPPORTED_EMOTIONS)}


@router.post("/analyze")
async def analyze(req: AnalyzeRequest) -> dict[str, Any]:
    return _analyze_payload(get_analyzer(), req.messages)


@router.post("/shift")
async def shift(req: ShiftRequest) -> dict[str, Any]:
    analyzer = get_analyzer()
    eng = get_engine()
    result, traits = analyzer.analyze_and_shift(req.messages, engine=eng)
    return {
        "analysis": result.to_dict(),
        "traits": traits,
        "locked": eng.locked_traits(),
        "baseline": eng.get_baseline(),
    }
