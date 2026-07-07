"""Conversation history service: SQLite persistence + LanceDB semantic search.

Stores conversation metadata and messages in SQLite for durable, transactional
CRUD. Each message is also embedded and indexed in LanceDB so conversations can
be located by semantic similarity to a natural-language query.

The SQLite path defaults to the user data directory (``~/.ganesh/data`` or
``$GANESH_DATA_DIR``) and the LanceDB URI defaults to a sibling directory.
Both are injectable for tests.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ganesh_backend.embeddings import (
    EmbedderProtocol,
    create_default_embedder,
)
from ganesh_backend.vector_store import LanceDbVectorStore

DEFAULT_COLLECTION = "ganesh_conversation_embeddings"
DEFAULT_LANCEDB_URI = ":memory:"
AUTO_TITLE_MAX_LEN = 50
DEFAULT_TITLE = "New Conversation"


def _default_sqlite_path() -> str:
    env_dir = os.environ.get("GANESH_DATA_DIR")
    if env_dir:
        base = Path(env_dir)
    else:
        base = Path.home() / ".ganesh" / "data"
    base.mkdir(parents=True, exist_ok=True)
    return str(base / "conversations.db")


def _default_lancedb_uri() -> str:
    env_dir = os.environ.get("GANESH_DATA_DIR")
    if env_dir:
        base = Path(env_dir)
    else:
        base = Path.home() / ".ganesh" / "data"
    base.mkdir(parents=True, exist_ok=True)
    return str(base / "lancedb")


class ConversationStore:
    """SQLite-backed conversation store with LanceDB semantic search.

    Parameters
    ----------
    sqlite_path:
        Filesystem path for the SQLite database. Defaults to the user data dir.
    lancedb_uri:
        LanceDB URI. ``":memory:"`` for in-memory (tests), or a filesystem path.
    embedder:
        Any object implementing :class:`EmbedderProtocol`. Defaults to the
        production embedder with a hash-based fallback.
    lancedb_collection:
        LanceDB table name for message embeddings.
    """

    def __init__(
        self,
        sqlite_path: Optional[str] = None,
        lancedb_uri: str = DEFAULT_LANCEDB_URI,
        embedder: Optional[EmbedderProtocol] = None,
        lancedb_collection: str = DEFAULT_COLLECTION,
    ) -> None:
        self._sqlite_path = sqlite_path or _default_sqlite_path()
        self._embedder = embedder or create_default_embedder()
        self._lancedb_collection = lancedb_collection
        self._store = LanceDbVectorStore(
            uri=lancedb_uri,
            collection_name=lancedb_collection,
            vector_dim=self._embedder.dimension,
            distance="cosine",
        )
        self._store.create_col(
            lancedb_collection, self._embedder.dimension, "cosine"
        )
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        # ``check_same_thread=False`` lets FastAPI's threadpool call into the
        # store from worker threads. SQLite serialises writes internally.
        conn = sqlite3.connect(self._sqlite_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    profile_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_conv "
                "ON messages(conversation_id)"
            )
            conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_conversation(
        self,
        title: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> str:
        """Create a new conversation and return its id."""
        conv_id = str(uuid.uuid4())
        now = self._now()
        final_title = title if title else DEFAULT_TITLE
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, profile_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (conv_id, final_title, profile_id, now, now),
            )
            conn.commit()
        return conv_id

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> str:
        """Append a message to a conversation, update title/updated_at, embed.

        Returns the new message id. Raises ``ValueError`` if the conversation
        does not exist.
        """
        msg_id = str(uuid.uuid4())
        now = self._now()
        with self._conn() as conn:
            conv = conn.execute(
                "SELECT id, title FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if conv is None:
                raise ValueError(f"Conversation {conversation_id} not found")

            conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (msg_id, conversation_id, role, content, now),
            )

            new_title = conv["title"]
            if conv["title"] == DEFAULT_TITLE and role == "user":
                new_title = content[:AUTO_TITLE_MAX_LEN]

            conn.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (new_title, now, conversation_id),
            )
            conn.commit()

        # Embed the message for semantic search (best-effort: never breaks
        # message persistence if the vector store has an issue).
        try:
            embedding = self._embedder.embed(content)
            payload = {
                "message_id": msg_id,
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "created_at": now,
            }
            self._store.insert(
                vectors=[embedding],
                payloads=[payload],
                ids=[msg_id],
            )
        except Exception:
            pass

        return msg_id

    def get_conversation(self, conversation_id: str) -> Optional[dict[str, Any]]:
        """Return a conversation dict (with messages) or ``None`` if not found."""
        with self._conn() as conn:
            conv = conn.execute(
                "SELECT id, title, profile_id, created_at, updated_at "
                "FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if conv is None:
                return None
            messages = conn.execute(
                "SELECT id, role, content, created_at FROM messages "
                "WHERE conversation_id = ? ORDER BY created_at ASC",
                (conversation_id,),
            ).fetchall()
        return {
            "id": conv["id"],
            "title": conv["title"],
            "profile_id": conv["profile_id"],
            "created_at": conv["created_at"],
            "updated_at": conv["updated_at"],
            "messages": [
                {
                    "id": m["id"],
                    "role": m["role"],
                    "content": m["content"],
                    "created_at": m["created_at"],
                }
                for m in messages
            ],
            "message_count": len(messages),
        }

    def list_conversations(self) -> list[dict[str, Any]]:
        """Return all conversations ordered by most-recently-updated first."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.profile_id, c.created_at, c.updated_at,
                       (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
                FROM conversations c
                ORDER BY c.updated_at DESC
                """
            ).fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "profile_id": r["profile_id"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "message_count": r["message_count"],
            }
            for r in rows
        ]

    def search_conversations(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Semantic search over conversation messages via LanceDB.

        Returns conversations ranked by best matching message, deduplicated.
        """
        if not query.strip():
            return []
        query_embedding = self._embedder.embed(query)
        results = self._store.search(
            query=query,
            vectors=query_embedding,
            top_k=limit * 4,
        )

        seen: set[str] = set()
        ordered_conv_ids: list[str] = []
        for r in results:
            conv_id = r.payload.get("conversation_id")
            if conv_id and conv_id not in seen:
                seen.add(conv_id)
                ordered_conv_ids.append(conv_id)
            if len(ordered_conv_ids) >= limit:
                break

        out: list[dict[str, Any]] = []
        for conv_id in ordered_conv_ids:
            conv = self.get_conversation(conv_id)
            if conv is not None:
                out.append(conv)
        return out

    def export_conversation(
        self,
        conversation_id: str,
        format: str,
    ) -> str:
        """Export a conversation as a JSON or Markdown string.

        Raises ``ValueError`` if the conversation does not exist or the
        format is unsupported.
        """
        conv = self.get_conversation(conversation_id)
        if conv is None:
            raise ValueError(f"Conversation {conversation_id} not found")

        if format == "json":
            return json.dumps(conv, indent=2, default=str)
        if format == "markdown":
            lines: list[str] = []
            lines.append(f"# {conv['title']}")
            lines.append("")
            lines.append(f"_Created: {conv['created_at']}_")
            lines.append(f"_Updated: {conv['updated_at']}_")
            lines.append("")
            for m in conv["messages"]:
                role_label = m["role"].capitalize()
                lines.append(f"**{role_label}**")
                lines.append("")
                lines.append(m["content"])
                lines.append("")
            return "\n".join(lines)
        raise ValueError(f"Unsupported export format: {format}")

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation, its messages, and LanceDB embeddings.

        Returns ``True`` if the conversation existed and was deleted.
        """
        conv = self.get_conversation(conversation_id)
        if conv is None:
            return False

        # Best-effort cleanup of LanceDB embeddings keyed by message id.
        for m in conv["messages"]:
            try:
                self._store.delete(m["id"])
            except Exception:
                pass

        with self._conn() as conn:
            conn.execute(
                "DELETE FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            conn.execute(
                "DELETE FROM conversations WHERE id = ?",
                (conversation_id,),
            )
            conn.commit()
        return True
