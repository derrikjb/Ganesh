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
                    updated_at TEXT NOT NULL,
                    summary TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    closed_at TEXT
                )
                """
            )
            columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(conversations)"
                ).fetchall()
            }
            if "summary" not in columns:
                conn.execute("ALTER TABLE conversations ADD COLUMN summary TEXT")
            if "status" not in columns:
                conn.execute(
                    "ALTER TABLE conversations ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
                )
            if "closed_at" not in columns:
                conn.execute("ALTER TABLE conversations ADD COLUMN closed_at TEXT")

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

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    start_message_id TEXT,
                    end_message_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_checkpoints_conv "
                "ON checkpoints(conversation_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_checkpoints_conv_seq "
                "ON checkpoints(conversation_id, sequence_number)"
            )
            conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_conversation(
        self,
        title: Optional[str] = None,
        profile_id: Optional[str] = None,
        status: str = "active",
    ) -> str:
        """Create a new conversation and return its id."""
        conv_id = str(uuid.uuid4())
        now = self._now()
        final_title = title if title else DEFAULT_TITLE
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, profile_id, created_at, updated_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (conv_id, final_title, profile_id, now, now, status),
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
        """Return a conversation dict (with messages and checkpoints) or ``None``."""
        with self._conn() as conn:
            conv = conn.execute(
                "SELECT id, title, profile_id, created_at, updated_at, "
                "summary, status, closed_at "
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
            checkpoints = conn.execute(
                "SELECT id, conversation_id, sequence_number, summary, "
                "start_message_id, end_message_id, created_at "
                "FROM checkpoints WHERE conversation_id = ? "
                "ORDER BY sequence_number ASC",
                (conversation_id,),
            ).fetchall()
        return {
            "id": conv["id"],
            "title": conv["title"],
            "profile_id": conv["profile_id"],
            "created_at": conv["created_at"],
            "updated_at": conv["updated_at"],
            "summary": conv["summary"],
            "status": conv["status"],
            "closed_at": conv["closed_at"],
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
            "checkpoints": [
                {
                    "id": c["id"],
                    "conversation_id": c["conversation_id"],
                    "sequence_number": c["sequence_number"],
                    "summary": c["summary"],
                    "start_message_id": c["start_message_id"],
                    "end_message_id": c["end_message_id"],
                    "created_at": c["created_at"],
                }
                for c in checkpoints
            ],
        }

    def list_conversations(self) -> list[dict[str, Any]]:
        """Return all conversations ordered by most-recently-updated first."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.profile_id, c.created_at, c.updated_at,
                       c.summary, c.status,
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
                "summary": r["summary"][:100] if r["summary"] else None,
                "status": r["status"],
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
        """Delete a conversation, its messages, checkpoints, and LanceDB embeddings.

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

        # Summary embedding cleanup (best-effort) — wired in Task 2.

        with self._conn() as conn:
            conn.execute(
                "DELETE FROM checkpoints WHERE conversation_id = ?",
                (conversation_id,),
            )
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

    # ------------------------------------------------------------------
    # Conversation lifecycle
    # ------------------------------------------------------------------

    def set_conversation_summary(
        self, conversation_id: str, summary: str
    ) -> None:
        """Set a conversation-level summary and mark the conversation closed."""
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                "UPDATE conversations SET summary = ?, status = 'closed', "
                "closed_at = ?, updated_at = ? WHERE id = ?",
                (summary, now, now, conversation_id),
            )
            conn.commit()

    def get_conversation_summary(self, conversation_id: str) -> Optional[str]:
        """Return the conversation-level summary, or ``None`` if not set."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT summary FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        val = row["summary"]
        return str(val) if val is not None else None

    def close_conversation(self, conversation_id: str) -> bool:
        """Mark a conversation as closed. Returns ``True`` if it existed."""
        now = self._now()
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE conversations SET status = 'closed', closed_at = ?, "
                "updated_at = ? WHERE id = ?",
                (now, now, conversation_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def get_conversation_status(self, conversation_id: str) -> Optional[str]:
        """Return ``'active'``, ``'closed'``, or ``None`` if not found."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT status FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        return str(row["status"])

    def get_last_message_timestamp(
        self, conversation_id: str
    ) -> Optional[str]:
        """Return the ``created_at`` of the most recent message, or ``None``."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT created_at FROM messages WHERE conversation_id = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        return str(row["created_at"])

    def get_active_conversation(
        self, profile_id: Optional[str]
    ) -> Optional[dict[str, Any]]:
        """Return the most recent active conversation for a profile, or ``None``."""
        with self._conn() as conn:
            if profile_id is None:
                row = conn.execute(
                    "SELECT id, title, profile_id, created_at, updated_at, "
                    "summary, status, closed_at FROM conversations "
                    "WHERE status = 'active' AND profile_id IS NULL "
                    "ORDER BY updated_at DESC LIMIT 1"
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id, title, profile_id, created_at, updated_at, "
                    "summary, status, closed_at FROM conversations "
                    "WHERE status = 'active' AND profile_id = ? "
                    "ORDER BY updated_at DESC LIMIT 1",
                    (profile_id,),
                ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "profile_id": row["profile_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "summary": row["summary"],
            "status": row["status"],
            "closed_at": row["closed_at"],
        }

    # ------------------------------------------------------------------
    # Checkpoint CRUD
    # ------------------------------------------------------------------

    def create_checkpoint(
        self,
        conversation_id: str,
        sequence_number: int,
        summary: str,
        start_message_id: Optional[str],
        end_message_id: Optional[str],
    ) -> str:
        """Insert a checkpoint and return its id."""
        cp_id = str(uuid.uuid4())
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO checkpoints "
                "(id, conversation_id, sequence_number, summary, "
                "start_message_id, end_message_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    cp_id,
                    conversation_id,
                    sequence_number,
                    summary,
                    start_message_id,
                    end_message_id,
                    now,
                ),
            )
            conn.commit()
        return cp_id

    def get_checkpoints(self, conversation_id: str) -> list[dict[str, Any]]:
        """Return all checkpoints for a conversation ordered by sequence."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, conversation_id, sequence_number, summary, "
                "start_message_id, end_message_id, created_at "
                "FROM checkpoints WHERE conversation_id = ? "
                "ORDER BY sequence_number ASC",
                (conversation_id,),
            ).fetchall()
        return [self._checkpoint_row_to_dict(r) for r in rows]

    def get_checkpoint(
        self, conversation_id: str, sequence_number: int
    ) -> Optional[dict[str, Any]]:
        """Return a specific checkpoint, or ``None`` if not found."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, conversation_id, sequence_number, summary, "
                "start_message_id, end_message_id, created_at "
                "FROM checkpoints WHERE conversation_id = ? "
                "AND sequence_number = ?",
                (conversation_id, sequence_number),
            ).fetchone()
        if row is None:
            return None
        return self._checkpoint_row_to_dict(row)

    def get_latest_checkpoint(
        self, conversation_id: str
    ) -> Optional[dict[str, Any]]:
        """Return the most recent checkpoint by sequence_number, or ``None``."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, conversation_id, sequence_number, summary, "
                "start_message_id, end_message_id, created_at "
                "FROM checkpoints WHERE conversation_id = ? "
                "ORDER BY sequence_number DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None
        return self._checkpoint_row_to_dict(row)

    def get_checkpoint_count(self, conversation_id: str) -> int:
        """Return the number of checkpoints for a conversation."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM checkpoints WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        return row["cnt"] if row else 0

    def get_messages_between(
        self,
        conversation_id: str,
        start_message_id: Optional[str],
        end_message_id: Optional[str],
    ) -> list[dict[str, Any]]:
        """Return messages in a segment bounded by message ids (inclusive).

        If ``start_message_id`` is ``None``, start from the beginning.
        If ``end_message_id`` is ``None``, go to the end.
        """
        with self._conn() as conn:
            all_rows = conn.execute(
                "SELECT id, role, content, created_at FROM messages "
                "WHERE conversation_id = ? ORDER BY created_at ASC",
                (conversation_id,),
            ).fetchall()

        rows = list(all_rows)
        if start_message_id is not None:
            start_idx = self._find_message_index(rows, start_message_id)
            if start_idx is not None:
                rows = rows[start_idx:]
            else:
                rows = []
        if end_message_id is not None:
            end_idx = self._find_message_index(rows, end_message_id)
            if end_idx is not None:
                rows = rows[: end_idx + 1]
            else:
                rows = []
        return [
            {
                "id": r["id"],
                "role": r["role"],
                "content": r["content"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def get_messages_since_checkpoint(
        self, conversation_id: str, checkpoint_sequence: int
    ) -> list[dict[str, Any]]:
        """Return messages after the end_message_id of the given checkpoint."""
        cp = self.get_checkpoint(conversation_id, checkpoint_sequence)
        if cp is None:
            return []
        end_msg_id = cp["end_message_id"]
        if end_msg_id is None:
            return self.get_messages_between(conversation_id, None, None)
        with self._conn() as conn:
            all_rows = conn.execute(
                "SELECT id, role, content, created_at FROM messages "
                "WHERE conversation_id = ? ORDER BY created_at ASC",
                (conversation_id,),
            ).fetchall()
        rows = list(all_rows)
        end_idx = self._find_message_index(rows, end_msg_id)
        if end_idx is None:
            return []
        rows = rows[end_idx + 1 :]
        return [
            {
                "id": r["id"],
                "role": r["role"],
                "content": r["content"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def delete_checkpoint(
        self, conversation_id: str, sequence_number: int
    ) -> bool:
        """Delete a checkpoint. Returns ``True`` if it existed."""
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM checkpoints WHERE conversation_id = ? "
                "AND sequence_number = ?",
                (conversation_id, sequence_number),
            )
            conn.commit()
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _checkpoint_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "conversation_id": row["conversation_id"],
            "sequence_number": row["sequence_number"],
            "summary": row["summary"],
            "start_message_id": row["start_message_id"],
            "end_message_id": row["end_message_id"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _find_message_index(
        rows: list[sqlite3.Row], message_id: str
    ) -> Optional[int]:
        for i, r in enumerate(rows):
            if r["id"] == message_id:
                return i
        return None
