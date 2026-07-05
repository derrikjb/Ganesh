"""Chat router: POST /chat with optional SSE streaming."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ganesh_backend.services import llm as llm_service

router = APIRouter(tags=["chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    model: str | None = None
    stream: bool = False


class ChatResponse(BaseModel):
    model: str
    content: str


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> Any:
    if req.stream:
        return StreamingResponse(
            _stream_response(req), media_type="text/event-stream"
        )

    try:
        response = llm_service.chat_completion(
            messages=[m.model_dump() for m in req.messages],
            model=req.model,
            stream=False,
        )
    except llm_service.MissingAPIKeyError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except llm_service.LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        content = response.choices[0].message.content
        model = response.model or req.model or llm_service.DEFAULT_MODEL
    except (AttributeError, IndexError) as exc:
        raise HTTPException(
            status_code=502, detail="Malformed LLM response"
        ) from exc

    return ChatResponse(model=model, content=content)


def _stream_response(req: ChatRequest) -> Any:
    try:
        response = llm_service.chat_completion(
            messages=[m.model_dump() for m in req.messages],
            model=req.model,
            stream=True,
        )
    except llm_service.MissingAPIKeyError as exc:
        yield _sse_chunk({"error": str(exc)}, event="error")
        return
    except llm_service.LLMError as exc:
        yield _sse_chunk({"error": str(exc)}, event="error")
        return

    for delta in llm_service.stream_chunks(response):
        yield _sse_chunk({"content": delta})

    yield _sse_chunk({"done": True}, event="done")


def _sse_chunk(data: dict[str, Any], event: str | None = None) -> str:
    payload = json.dumps(data)
    if event:
        return f"event: {event}\ndata: {payload}\n\n"
    return f"data: {payload}\n\n"
