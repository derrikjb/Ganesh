"""Chat router: POST /chat with optional SSE streaming.

Error handling (Task 40):
    - ``MissingAPIKeyError`` → HTTP 401 with a friendly message prompting
      the user to re-enter their API key in settings. The sidecar does NOT
      crash — the error is surfaced as a normal HTTP response.
    - LiteLLM ``AuthenticationError`` (raised when a previously-valid key is
      revoked/rotated) is also mapped to 401 with the same friendly message.
    - All other LLM errors → HTTP 400 with the underlying message.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ganesh_backend.services import llm as llm_service

router = APIRouter(tags=["chat"])

_INVALID_KEY_MESSAGE = (
    "Your API key is invalid or has been revoked. "
    "Open Settings → Providers to update your API key."
)


def _is_auth_error(exc: Exception) -> bool:
    """Detect LiteLLM/SDK authentication errors (rotated/revoked keys)."""
    msg = str(exc).lower()
    if "authenticationerror" in msg or "invalid_api_key" in msg:
        return True
    if "401" in msg and ("api key" in msg or "unauthorized" in msg):
        return True
    type_name = type(exc).__name__
    return type_name in {"AuthenticationError", "PermissionDeniedError"}


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    provider: str = llm_service.DEFAULT_PROVIDER
    model: str | None = None
    stream: bool = False


class ChatResponse(BaseModel):
    provider: str
    model: str
    content: str


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> Any:
    if req.provider not in llm_service.SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown provider: {req.provider!r}. "
                f"Supported: {', '.join(llm_service.SUPPORTED_PROVIDERS)}"
            ),
        )

    if req.stream:
        return StreamingResponse(
            _stream_response(req), media_type="text/event-stream"
        )

    try:
        response = llm_service.chat_completion(
            messages=[m.model_dump() for m in req.messages],
            provider=req.provider,
            model=req.model,
            stream=False,
        )
    except llm_service.MissingAPIKeyError as exc:
        raise HTTPException(
            status_code=401,
            detail=f"API key invalid or missing: {exc}",
        ) from exc
    except llm_service.UnsupportedProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except llm_service.LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except llm_service.UnsupportedProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        content = response.choices[0].message.content
        model = response.model or req.model or llm_service.DEFAULT_MODEL
    except (AttributeError, IndexError) as exc:
        raise HTTPException(
            status_code=502, detail="Malformed LLM response"
        ) from exc

    return ChatResponse(provider=req.provider, model=model, content=content)


def _stream_response(req: ChatRequest) -> Any:
    try:
        response = llm_service.chat_completion(
            messages=[m.model_dump() for m in req.messages],
            provider=req.provider,
            model=req.model,
            stream=True,
        )
    except llm_service.MissingAPIKeyError as exc:
        yield _sse_chunk(
            {"error": f"API key invalid or missing: {exc}", "code": 401},
            event="error",
        )
        return
    except llm_service.UnsupportedProviderError as exc:
        yield _sse_chunk({"error": str(exc)}, event="error")
        return
    except llm_service.LLMError as exc:
        yield _sse_chunk({"error": str(exc)}, event="error")
        return
    except llm_service.LLMError as exc:
        if _is_auth_error(exc):
            llm_service.reset_api_key_cache()
            yield _sse_chunk(
                {"error": _INVALID_KEY_MESSAGE, "code": 401}, event="error"
            )
        else:
            yield _sse_chunk({"error": str(exc)}, event="error")
        return
    except llm_service.UnsupportedProviderError as exc:
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
