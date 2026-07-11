"""LanceDB-backed store for conversation summary embeddings.

Two embedding collections support the checkpoint memory system:

- **Checkpoint summaries** — one embedding per checkpoint within a conversation.
  Used for on-demand transcript pull: when a user message semantically matches
  an old checkpoint, the full message segment is pulled into the context window.

- **Conversation summaries** — one embedding per conversation (generated on
  close). Used for cross-day memory retrieval: relevant past conversation
  summaries are injected into new conversations.

Both collections reuse the existing :class:`LanceDbVectorStore` adapter and
:class:`EmbedderProtocol` infrastructure — no separate embedding model is
created.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ganesh_backend.embeddings import (
    EmbedderProtocol,
    create_default_embedder,
)
from ganesh_backend.vector_store import LanceDbVectorStore

CHECKPOINT_COLLECTION = "ganesh_checkpoint_summaries"
CONVERSATION_COLLECTION = "ganesh_conversation_summaries"
DEFAULT_LANCEDB_URI = ":memory:"


def _default_lancedb_uri() -> str:
    env_dir = os.environ.get("GANESH_DATA_DIR")
    if env_dir:
        base = Path(env_dir)
    else:
        base = Path.home() / ".ganesh" / "data"
    base.mkdir(parents=True, exist_ok=True)
    return str(base / "lancedb")


@dataclass
class CheckpointSearchResult:
    checkpoint_id: str
    conversation_id: str
    sequence_number: int
    summary: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationSearchResult:
    conversation_id: str
    summary: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class SummaryEmbeddingStore:
    """LanceDB store for conversation summary embeddings.

    Parameters
    ----------
    uri:
        LanceDB URI. ``":memory:"`` for in-memory (tests), or a filesystem
        path for persistence.
    embedder:
        Any object implementing :class:`EmbedderProtocol`.
    """

    def __init__(
        self,
        uri: str = DEFAULT_LANCEDB_URI,
        embedder: Optional[EmbedderProtocol] = None,
    ) -> None:
        self._uri = uri
        self._embedder = embedder or create_default_embedder()
        self._checkpoint_collection = CHECKPOINT_COLLECTION
        self._conversation_collection = CONVERSATION_COLLECTION

        self._checkpoint_store = LanceDbVectorStore(
            uri=uri,
            collection_name=self._checkpoint_collection,
            vector_dim=self._embedder.dimension,
            distance="cosine",
        )
        self._checkpoint_store.create_col(
            self._checkpoint_collection,
            self._embedder.dimension,
            "cosine",
        )

        self._conversation_store = LanceDbVectorStore(
            uri=uri,
            collection_name=self._conversation_collection,
            vector_dim=self._embedder.dimension,
            distance="cosine",
        )
        self._conversation_store.create_col(
            self._conversation_collection,
            self._embedder.dimension,
            "cosine",
        )

    def index_checkpoint_summary(
        self,
        checkpoint_id: str,
        conversation_id: str,
        sequence_number: int,
        summary: str,
        metadata: dict[str, Any],
    ) -> None:
        """Embed and store a checkpoint summary (upsert by checkpoint_id)."""
        payload: dict[str, Any] = {
            "checkpoint_id": checkpoint_id,
            "conversation_id": conversation_id,
            "sequence_number": sequence_number,
            "summary": summary,
        }
        payload.update(metadata)
        embedding = self._embedder.embed(summary)
        existing = self._checkpoint_store.get(checkpoint_id)
        if existing is not None:
            self._checkpoint_store.update(
                vector_id=checkpoint_id,
                vector=embedding,
                payload=payload,
            )
        else:
            self._checkpoint_store.insert(
                vectors=[embedding],
                payloads=[payload],
                ids=[checkpoint_id],
            )

    def search_checkpoint_summaries(
        self,
        query: str,
        conversation_id: str,
        limit: int = 5,
    ) -> list[CheckpointSearchResult]:
        """Semantic search within a single conversation's checkpoint summaries."""
        if not query.strip():
            return []
        query_embedding = self._embedder.embed(query)
        pool_limit = max(limit * 10, 50)
        results = self._checkpoint_store.search(
            query=query,
            vectors=query_embedding,
            top_k=pool_limit,
            filters={"conversation_id": conversation_id},
        )
        out: list[CheckpointSearchResult] = []
        for r in results:
            if r.payload.get("conversation_id") != conversation_id:
                continue
            metadata = {
                k: v
                for k, v in r.payload.items()
                if k not in ("checkpoint_id", "conversation_id",
                             "sequence_number", "summary")
            }
            out.append(
                CheckpointSearchResult(
                    checkpoint_id=r.payload.get("checkpoint_id", r.id),
                    conversation_id=r.payload.get("conversation_id", ""),
                    sequence_number=int(r.payload.get("sequence_number", 0)),
                    summary=r.payload.get("summary", ""),
                    score=r.score,
                    metadata=metadata,
                )
            )
            if len(out) >= limit:
                break
        return out

    def delete_checkpoint_summary(self, checkpoint_id: str) -> None:
        """Delete a single checkpoint summary by its checkpoint_id."""
        self._checkpoint_store.delete(checkpoint_id)

    def delete_conversation_checkpoints(self, conversation_id: str) -> None:
        """Delete all checkpoint embeddings for a given conversation."""
        all_rows = self._checkpoint_store.list(top_k=None)
        for r in all_rows:
            if r.payload.get("conversation_id") == conversation_id:
                try:
                    self._checkpoint_store.delete(r.id)
                except Exception:
                    pass

    def index_conversation_summary(
        self,
        conversation_id: str,
        summary: str,
        metadata: dict[str, Any],
    ) -> None:
        """Embed and store a conversation-level summary (upsert by conversation_id)."""
        payload: dict[str, Any] = {
            "conversation_id": conversation_id,
            "summary": summary,
        }
        payload.update(metadata)
        embedding = self._embedder.embed(summary)
        existing = self._conversation_store.get(conversation_id)
        if existing is not None:
            self._conversation_store.update(
                vector_id=conversation_id,
                vector=embedding,
                payload=payload,
            )
        else:
            self._conversation_store.insert(
                vectors=[embedding],
                payloads=[payload],
                ids=[conversation_id],
            )

    def search_conversation_summaries(
        self,
        query: str,
        exclude_conversation_id: Optional[str] = None,
        limit: int = 5,
    ) -> list[ConversationSearchResult]:
        """Semantic search across all conversation-level summaries."""
        if not query.strip():
            return []
        query_embedding = self._embedder.embed(query)
        pool_limit = max(limit * 10, 50)
        results = self._conversation_store.search(
            query=query,
            vectors=query_embedding,
            top_k=pool_limit,
        )
        out: list[ConversationSearchResult] = []
        for r in results:
            conv_id = r.payload.get("conversation_id", r.id)
            if exclude_conversation_id is not None and conv_id == exclude_conversation_id:
                continue
            metadata = {
                k: v
                for k, v in r.payload.items()
                if k not in ("conversation_id", "summary")
            }
            out.append(
                ConversationSearchResult(
                    conversation_id=conv_id,
                    summary=r.payload.get("summary", ""),
                    score=r.score,
                    metadata=metadata,
                )
            )
            if len(out) >= limit:
                break
        return out

    def delete_conversation_summary(self, conversation_id: str) -> None:
        """Delete a conversation-level summary by its conversation_id."""
        self._conversation_store.delete(conversation_id)


_store: Optional[SummaryEmbeddingStore] = None


def get_summary_embedding_store() -> SummaryEmbeddingStore:
    global _store
    if _store is None:
        _store = SummaryEmbeddingStore(
            uri=_default_lancedb_uri(),
            embedder=create_default_embedder(),
        )
    return _store


def reset_summary_embedding_store() -> None:
    global _store
    _store = None


def set_summary_embedding_store(store: SummaryEmbeddingStore) -> None:
    global _store
    _store = store
