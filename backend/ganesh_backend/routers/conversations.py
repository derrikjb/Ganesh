"""FastAPI router for conversation history endpoints.

Endpoints
---------
POST   /api/conversations                              — create conversation
GET    /api/conversations                              — list conversations
GET    /api/conversations/search                       — semantic search (?q=)
GET    /api/conversations/{id}                         — get conversation with messages
POST   /api/conversations/{id}/export                  — export (json|markdown)
DELETE /api/conversations/{id}                         — delete conversation
POST   /api/conversations/{id}/messages                — append a message
POST   /api/conversations/{id}/close                   — close + summarize
GET    /api/conversations/{id}/checkpoints              — list checkpoints
GET    /api/conversations/{id}/checkpoints/{seq}/messages — checkpoint segment
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ganesh_backend.embeddings import create_default_embedder
from ganesh_backend.services.conversations import ConversationStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _data_dir() -> Path:
    env_dir = os.environ.get("GANESH_DATA_DIR")
    if env_dir:
        path = Path(env_dir)
    else:
        path = Path.home() / ".ganesh" / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _default_sqlite_path() -> str:
    return str(_data_dir() / "conversations.db")


def _default_lancedb_uri() -> str:
    return str(_data_dir() / "lancedb")


_service: Optional[ConversationStore] = None


def get_conversation_service() -> ConversationStore:
    global _service
    if _service is None:
        _service = ConversationStore(
            sqlite_path=_default_sqlite_path(),
            lancedb_uri=_default_lancedb_uri(),
            embedder=create_default_embedder(),
        )
    return _service


def reset_conversation_service() -> None:
    global _service
    _service = None


def set_conversation_service(store: ConversationStore) -> None:
    global _service
    _service = store


class CreateConversationRequest(BaseModel):
    title: Optional[str] = None
    profile_id: Optional[str] = None


class AddMessageRequest(BaseModel):
    role: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)


class ExportRequest(BaseModel):
    format: str = Field("json", pattern="^(json|markdown)$")


class ConversationSummary(BaseModel):
    id: str
    title: str
    profile_id: Optional[str]
    created_at: str
    updated_at: str
    message_count: int
    summary: Optional[str] = None
    status: str = "active"
    closed_at: Optional[str] = None


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class CheckpointOut(BaseModel):
    id: str
    conversation_id: str
    sequence_number: int
    summary: str
    start_message_id: Optional[str] = None
    end_message_id: Optional[str] = None
    created_at: str


class ConversationDetail(BaseModel):
    id: str
    title: str
    profile_id: Optional[str]
    created_at: str
    updated_at: str
    messages: list[MessageOut]
    message_count: int
    summary: Optional[str] = None
    status: str = "active"
    closed_at: Optional[str] = None
    checkpoints: list[CheckpointOut] = []


class ListResponse(BaseModel):
    conversations: list[ConversationSummary]


class SearchResponse(BaseModel):
    query: str
    results: list[ConversationDetail]


class CreateResponse(BaseModel):
    id: str


class AddMessageResponse(BaseModel):
    id: str


class ExportResponse(BaseModel):
    format: str
    content: str


class CloseResponse(BaseModel):
    conversation_id: str
    summary: Optional[str] = None
    status: str
    checkpoint_count: int


@router.post("", response_model=CreateResponse, status_code=201)
async def create_conversation(req: CreateConversationRequest) -> CreateResponse:
    service = get_conversation_service()
    conv_id = service.create_conversation(title=req.title, profile_id=req.profile_id)
    return CreateResponse(id=conv_id)


@router.get("", response_model=ListResponse)
async def list_conversations() -> ListResponse:
    service = get_conversation_service()
    convs = service.list_conversations()
    return ListResponse(
        conversations=[ConversationSummary(**c) for c in convs]
    )


@router.get("/search", response_model=SearchResponse)
async def search_conversations(
    q: str = Query(..., min_length=1, alias="q"),
    limit: int = Query(10, ge=1, le=50),
) -> SearchResponse:
    service = get_conversation_service()
    results = service.search_conversations(query=q, limit=limit)
    return SearchResponse(
        query=q,
        results=[ConversationDetail(**r) for r in results],
    )


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str) -> ConversationDetail:
    service = get_conversation_service()
    conv = service.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")
    return ConversationDetail(**conv)


@router.post("/{conversation_id}/export", response_model=ExportResponse)
async def export_conversation(
    conversation_id: str,
    req: ExportRequest,
) -> ExportResponse:
    service = get_conversation_service()
    try:
        content = service.export_conversation(conversation_id, format=req.format)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ExportResponse(format=req.format, content=content)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str) -> None:
    service = get_conversation_service()
    deleted = service.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Conversation {conversation_id} not found")


@router.post(
    "/{conversation_id}/messages",
    response_model=AddMessageResponse,
    status_code=201,
)
async def add_message(
    conversation_id: str,
    req: AddMessageRequest,
) -> AddMessageResponse:
    service = get_conversation_service()
    try:
        msg_id = service.add_message(
            conversation_id=conversation_id,
            role=req.role,
            content=req.content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AddMessageResponse(id=msg_id)


@router.post(
    "/{conversation_id}/close",
    response_model=CloseResponse,
)
async def close_conversation_endpoint(
    conversation_id: str,
) -> CloseResponse:
    service = get_conversation_service()
    conv = service.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conversation_id} not found",
        )

    if conv["status"] == "closed":
        return CloseResponse(
            conversation_id=conversation_id,
            summary=conv.get("summary"),
            status="closed",
            checkpoint_count=service.get_checkpoint_count(conversation_id),
        )

    try:
        from ganesh_backend.services.summary import get_summary_service

        summary_service = get_summary_service()
        summary_service.generate_checkpoint(conversation_id)
        summary = summary_service.generate_conversation_summary(conversation_id)
    except Exception:
        logger.exception(
            "Summary generation failed for conversation %s; closing without summary",
            conversation_id,
        )
        service.close_conversation(conversation_id)
        summary = None

    status = service.get_conversation_status(conversation_id) or "closed"
    checkpoint_count = service.get_checkpoint_count(conversation_id)
    return CloseResponse(
        conversation_id=conversation_id,
        summary=summary,
        status=status,
        checkpoint_count=checkpoint_count,
    )


@router.get(
    "/{conversation_id}/checkpoints",
    response_model=list[CheckpointOut],
)
async def get_checkpoints_endpoint(
    conversation_id: str,
) -> list[CheckpointOut]:
    service = get_conversation_service()
    if service.get_conversation(conversation_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conversation_id} not found",
        )
    checkpoints = service.get_checkpoints(conversation_id)
    return [CheckpointOut(**c) for c in checkpoints]


@router.get(
    "/{conversation_id}/checkpoints/{seq}/messages",
    response_model=list[MessageOut],
)
async def get_checkpoint_messages_endpoint(
    conversation_id: str,
    seq: int,
) -> list[MessageOut]:
    service = get_conversation_service()
    checkpoint = service.get_checkpoint(conversation_id, seq)
    if checkpoint is None:
        raise HTTPException(
            status_code=404,
            detail=f"Checkpoint {seq} not found for conversation {conversation_id}",
        )
    messages = service.get_messages_between(
        conversation_id,
        checkpoint.get("start_message_id"),
        checkpoint.get("end_message_id"),
    )
    return [MessageOut(**m) for m in messages]
