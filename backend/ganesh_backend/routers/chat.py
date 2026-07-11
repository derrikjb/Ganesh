"""Chat router: POST /chat with optional SSE streaming.

Error handling (Task 40):
    - ``MissingAPIKeyError`` → HTTP 401 with a friendly message prompting
      the user to re-enter their API key in settings. The sidecar does NOT
      crash — the error is surfaced as a normal HTTP response.
    - LiteLLM ``AuthenticationError`` (raised when a previously-valid key is
      revoked/rotated) is also mapped to 401 with the same friendly message.
    - All other LLM errors → HTTP 400 with the underlying message.

Conversation memory (Task 7):
    - When ``conversation_memory.enabled`` is True, the router accepts an
      optional ``conversation_id``. If absent, a new conversation is created
      (closing any active conversation for the same profile first). If present
      and active, a gap > ``checkpoint_gap_seconds`` triggers a checkpoint
      summary but the SAME conversation continues. Messages are persisted
      server-side and the context window is assembled with checkpoint
      summaries, cross-day memory, and on-demand transcript pulls.
    - When disabled, the router falls back to pure passthrough behaviour
      (backward compatible with clients that never send ``conversation_id``).
    - Streaming responses emit an initial ``event: conversation`` SSE event
      carrying the ``conversation_id`` so the frontend can track it.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ganesh_backend.services import llm as llm_service
from ganesh_backend.services.config import config_service
from ganesh_backend.services.conversations import ConversationStore
from ganesh_backend.routers.conversations import get_conversation_service

logger = logging.getLogger(__name__)

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


def _memory_enabled() -> bool:
    """Return True if the conversation-checkpoint memory system is active."""
    return bool(
        config_service.get_setting("conversation_memory.enabled", True)
    )


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    provider: str = llm_service.DEFAULT_PROVIDER
    model: str | None = None
    stream: bool = False
    conversation_id: Optional[str] = None
    profile_id: Optional[str] = None


class ChatResponse(BaseModel):
    provider: str
    model: str
    content: str
    conversation_id: str


# ---------------------------------------------------------------------------
# Helpers (conversation memory)
# ---------------------------------------------------------------------------


def _parse_timestamp(ts: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into a timezone-aware datetime."""
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _ensure_conversation(req: ChatRequest) -> str:
    """Resolve or create the conversation id for this chat turn.

    - If ``conversation_id`` is provided and active, check the gap since the
      last message. A gap > ``checkpoint_gap_seconds`` triggers a checkpoint
      summary but the SAME conversation continues (no new conversation).
    - If the conversation is closed or unknown, create a new one.
    - If ``conversation_id`` is absent, close any active conversation for the
      profile (generating a conversation-level summary) then create a new one.
    """
    store = get_conversation_service()
    gap_seconds = int(
        config_service.get_setting(
            "conversation_memory.checkpoint_gap_seconds", 300
        )
    )

    if req.conversation_id:
        status = store.get_conversation_status(req.conversation_id)
        if status == "active":
            _maybe_checkpoint(store, req.conversation_id, gap_seconds)
            return req.conversation_id
        return _create_new_conversation(store, req.profile_id)

    _close_active_conversation(store, req.profile_id)
    return _create_new_conversation(store, req.profile_id)


def _maybe_checkpoint(
    store: ConversationStore, conversation_id: str, gap_seconds: int
) -> None:
    """Trigger a checkpoint summary if the gap since the last message is large."""
    last_ts = store.get_last_message_timestamp(conversation_id)
    if last_ts is None:
        return
    last_dt = _parse_timestamp(last_ts)
    if last_dt is None:
        return
    now = datetime.now(timezone.utc)
    if (now - last_dt).total_seconds() <= gap_seconds:
        return

    try:
        from ganesh_backend.services.summary import get_summary_service

        summary_service = get_summary_service()
        checkpoint = summary_service.generate_checkpoint(conversation_id)
        if checkpoint is not None:
            logger.info(
                "Created checkpoint %s for conversation %s",
                checkpoint.get("sequence_number"),
                conversation_id,
            )
    except Exception:
        logger.exception(
            "Checkpoint generation failed for conversation %s",
            conversation_id,
        )


def _close_active_conversation(
    store: ConversationStore, profile_id: Optional[str]
) -> None:
    """Close any active conversation for the profile with a summary."""
    active = store.get_active_conversation(profile_id)
    if active is None:
        return
    active_id = active["id"]
    try:
        from ganesh_backend.services.summary import get_summary_service

        summary_service = get_summary_service()
        summary_service.generate_conversation_summary(active_id)
    except Exception:
        logger.exception(
            "Failed to generate conversation summary for %s", active_id
        )
        store.close_conversation(active_id)


def _create_new_conversation(
    store: ConversationStore, profile_id: Optional[str]
) -> str:
    """Create a new conversation and return its id."""
    return store.create_conversation(profile_id=profile_id)


def _persist_message(
    conversation_id: str, role: str, content: str
) -> Optional[str]:
    """Persist a message to the conversation store (best-effort).

    Returns the message id, or ``None`` if persistence failed.
    """
    store = get_conversation_service()
    try:
        return store.add_message(
            conversation_id=conversation_id,
            role=role,
            content=content,
        )
    except Exception:
        logger.exception(
            "Failed to persist %s message to conversation %s",
            role,
            conversation_id,
        )
        return None


def _assemble_context(
    messages: list[dict[str, Any]],
    user_message: str,
    conversation_id: str,
) -> list[dict[str, Any]]:
    """Build the full context window via ContextAssemblyService.

    Prepends checkpoint summaries, cross-day memory, and on-demand transcript
    pulls as system messages before the existing message array.
    """
    try:
        from ganesh_backend.services.summary_retrieval import (
            get_context_assembly_service,
        )

        service = get_context_assembly_service()
        return service.build_context(
            user_message=user_message,
            conversation_id=conversation_id,
            existing_messages=messages,
        )
    except Exception:
        logger.exception(
            "Context assembly failed for conversation %s; falling back",
            conversation_id,
        )
        return messages


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


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

    conv_id: Optional[str] = None
    if _memory_enabled():
        conv_id = _ensure_conversation(req)
        last_user_msg = req.messages[-1]
        if last_user_msg.role == "user":
            _persist_message(conv_id, "user", last_user_msg.content)
        messages = _assemble_context(
            [m.model_dump() for m in req.messages],
            last_user_msg.content,
            conv_id,
        )
    else:
        messages = [m.model_dump() for m in req.messages]

    try:
        response = llm_service.chat_completion(
            messages=messages,
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
        if _is_auth_error(exc):
            llm_service.reset_api_key_cache()
            raise HTTPException(
                status_code=401,
                detail=_INVALID_KEY_MESSAGE,
            ) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        content = response.choices[0].message.content
        model = response.model or req.model or llm_service.DEFAULT_MODEL
    except (AttributeError, IndexError) as exc:
        raise HTTPException(
            status_code=502, detail="Malformed LLM response"
        ) from exc

    if conv_id is not None:
        _persist_message(conv_id, "assistant", content)

    return ChatResponse(
        provider=req.provider,
        model=model,
        content=content,
        conversation_id=conv_id or "",
    )


def _stream_response(req: ChatRequest) -> Any:
    """Stream the LLM response as SSE chunks.

    When conversation memory is enabled, emits an initial
    ``event: conversation`` event carrying the ``conversation_id`` before
    streaming the LLM deltas. The assistant response is persisted after the
    stream completes.
    """
    conv_id: Optional[str] = None
    if _memory_enabled():
        conv_id = _ensure_conversation(req)
        last_user_msg = req.messages[-1]
        if last_user_msg.role == "user":
            _persist_message(conv_id, "user", last_user_msg.content)
        messages = _assemble_context(
            [m.model_dump() for m in req.messages],
            last_user_msg.content,
            conv_id,
        )
        yield _sse_chunk(
            {"conversation_id": conv_id}, event="conversation"
        )
    else:
        messages = [m.model_dump() for m in req.messages]

    try:
        response = llm_service.chat_completion(
            messages=messages,
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
        if _is_auth_error(exc):
            llm_service.reset_api_key_cache()
            yield _sse_chunk(
                {"error": _INVALID_KEY_MESSAGE, "code": 401}, event="error"
            )
        else:
            yield _sse_chunk({"error": str(exc)}, event="error")
        return

    accumulated: list[str] = []
    for delta in llm_service.stream_chunks(response):
        accumulated.append(delta)
        yield _sse_chunk({"content": delta})

    if conv_id is not None and accumulated:
        _persist_message(conv_id, "assistant", "".join(accumulated))

    yield _sse_chunk({"done": True}, event="done")


def _sse_chunk(data: dict[str, Any], event: str | None = None) -> str:
    payload = json.dumps(data)
    if event:
        return f"event: {event}\ndata: {payload}\n\n"
    return f"data: {payload}\n\n"
