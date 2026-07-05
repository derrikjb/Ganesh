"""Memory service: explicit CRUD over LanceDB + local embeddings.

This service provides a thin, explicit API for storing, retrieving,
updating, and deleting memories. It uses LanceDB as the vector store
(via :class:`LanceDbVectorStore`) and a pluggable local embedder (default:
sentence-transformers; tests: deterministic hash-based).

The service intentionally avoids mem0's ``Memory`` class (which requires an
LLM for memory extraction) — automatic extraction from chat is a separate
task. Instead, it uses the LanceDB adapter directly, which itself implements
mem0's ``VectorStoreBase`` interface for future integration.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from ganesh_backend.embeddings import (
    DEFAULT_EMBEDDING_DIM,
    EmbedderProtocol,
    HashEmbedder,
    create_default_embedder,
)
from ganesh_backend.vector_store import LanceDbVectorStore

DEFAULT_COLLECTION = "ganesh_memories"
DEFAULT_DB_PATH = ":memory:"


class MemoryRecord:
    """A single memory entry returned by the service."""

    def __init__(
        self,
        id: str,
        content: str,
        metadata: dict[str, Any],
        created_at: str,
        updated_at: str,
    ) -> None:
        self.id = id
        self.content = content
        self.metadata = metadata
        self.created_at = created_at
        self.updated_at = updated_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class MemoryService:
    """Explicit CRUD memory service backed by LanceDB.

    Parameters
    ----------
    db_path:
        LanceDB URI. ``":memory:"`` for in-memory (tests), or a filesystem
        path for persistent storage.
    embedder:
        Any object implementing :class:`EmbedderProtocol`. Defaults to
        sentence-transformers with a hash-based fallback.
    collection_name:
        LanceDB table name.
    """

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        embedder: Optional[EmbedderProtocol] = None,
        collection_name: str = DEFAULT_COLLECTION,
    ) -> None:
        self._embedder = embedder or create_default_embedder()
        self._store = LanceDbVectorStore(
            uri=db_path,
            collection_name=collection_name,
            vector_dim=self._embedder.dimension,
            distance="cosine",
        )
        self._store.create_col(collection_name, self._embedder.dimension, "cosine")

    def store_memory(
        self,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> MemoryRecord:
        memory_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        full_metadata = {
            "content": content,
            "user_metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }
        embedding = self._embedder.embed(content)
        self._store.insert(
            vectors=[embedding],
            payloads=[full_metadata],
            ids=[memory_id],
        )
        return MemoryRecord(
            id=memory_id,
            content=content,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )

    def retrieve_memories(
        self,
        query: str,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        query_embedding = self._embedder.embed(query)
        results = self._store.search(
            query=query,
            vectors=query_embedding,
            top_k=limit,
        )
        records: list[MemoryRecord] = []
        for result in results:
            payload = result.payload
            records.append(
                MemoryRecord(
                    id=result.id,
                    content=payload.get("content", ""),
                    metadata=payload.get("user_metadata", {}),
                    created_at=payload.get("created_at", ""),
                    updated_at=payload.get("updated_at", ""),
                )
            )
        return records

    def update_memory(
        self,
        memory_id: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[MemoryRecord]:
        existing = self._store.get(memory_id)
        if existing is None:
            return None
        old_payload = existing.payload
        now = datetime.now(timezone.utc).isoformat()
        new_metadata = metadata if metadata is not None else old_payload.get("user_metadata", {})
        full_metadata = {
            "content": content,
            "user_metadata": new_metadata,
            "created_at": old_payload.get("created_at", now),
            "updated_at": now,
        }
        new_embedding = self._embedder.embed(content)
        self._store.update(
            vector_id=memory_id,
            vector=new_embedding,
            payload=full_metadata,
        )
        return MemoryRecord(
            id=memory_id,
            content=content,
            metadata=new_metadata,
            created_at=full_metadata["created_at"],
            updated_at=now,
        )

    def delete_memory(self, memory_id: str) -> bool:
        existing = self._store.get(memory_id)
        if existing is None:
            return False
        self._store.delete(memory_id)
        return True

    def list_memories(self) -> list[MemoryRecord]:
        results = self._store.list()
        records: list[MemoryRecord] = []
        for result in results:
            payload = result.payload
            records.append(
                MemoryRecord(
                    id=result.id,
                    content=payload.get("content", ""),
                    metadata=payload.get("user_metadata", {}),
                    created_at=payload.get("created_at", ""),
                    updated_at=payload.get("updated_at", ""),
                )
            )
        return records
