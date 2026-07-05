"""Shared bridge memory layer: explicit per-memory cross-profile grants.

A bridge grant allows one profile (the *receiving* profile) to semantically
query a specific memory owned by another profile (the *granting* profile).
Grants are explicit and per-memory — there is no blanket access.

Every bridge query is recorded in ``bridge_access_log`` for audit purposes.

Schema (SQLite)::

    bridge_grants (
        id                   TEXT PRIMARY KEY,
        granting_profile_id  TEXT NOT NULL,
        receiving_profile_id TEXT NOT NULL,
        memory_id            TEXT NOT NULL,
        created_at           TEXT NOT NULL
    )

    bridge_access_log (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        receiving_profile_id TEXT NOT NULL,
        granting_profile_id  TEXT NOT NULL,
        query                TEXT NOT NULL,
        timestamp            TEXT NOT NULL
    )

The bridge service depends on :class:`MemoryService` for semantic search and
on :class:`ProfileManager` for profile validation. Both are injected via the
singleton getters by the router; tests inject explicit instances.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ganesh_backend.services.memory import MemoryRecord, MemoryService


_SCHEMA = """
CREATE TABLE IF NOT EXISTS bridge_grants (
    id                   TEXT PRIMARY KEY,
    granting_profile_id  TEXT NOT NULL,
    receiving_profile_id TEXT NOT NULL,
    memory_id            TEXT NOT NULL,
    created_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bridge_access_log (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    receiving_profile_id TEXT NOT NULL,
    granting_profile_id  TEXT NOT NULL,
    query                TEXT NOT NULL,
    timestamp            TEXT NOT NULL
);
"""


def _default_db_path() -> str:
    env_dir = os.environ.get("GANESH_DATA_DIR")
    if env_dir:
        base = Path(env_dir)
    else:
        base = Path.home() / ".ganesh"
    base.mkdir(parents=True, exist_ok=True)
    return str(base / "bridge.db")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BridgeGrant:
    id: str
    granting_profile_id: str
    receiving_profile_id: str
    memory_id: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "granting_profile_id": self.granting_profile_id,
            "receiving_profile_id": self.receiving_profile_id,
            "memory_id": self.memory_id,
            "created_at": self.created_at,
        }


@dataclass
class AuditEntry:
    id: int
    receiving_profile_id: str
    granting_profile_id: str
    query: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "receiving_profile_id": self.receiving_profile_id,
            "granting_profile_id": self.granting_profile_id,
            "query": self.query,
            "timestamp": self.timestamp,
        }


def _grant_from_row(row: sqlite3.Row) -> BridgeGrant:
    return BridgeGrant(
        id=row["id"],
        granting_profile_id=row["granting_profile_id"],
        receiving_profile_id=row["receiving_profile_id"],
        memory_id=row["memory_id"],
        created_at=row["created_at"],
    )


def _audit_from_row(row: sqlite3.Row) -> AuditEntry:
    return AuditEntry(
        id=row["id"],
        receiving_profile_id=row["receiving_profile_id"],
        granting_profile_id=row["granting_profile_id"],
        query=row["query"],
        timestamp=row["timestamp"],
    )


class BridgeService:
    """Explicit per-memory cross-profile grant store + audit log."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        memory_service: Optional[MemoryService] = None,
    ) -> None:
        self._db_path: str = db_path or _default_db_path()
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection = sqlite3.connect(
            self._db_path, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._memory_service = memory_service
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def set_memory_service(self, service: MemoryService) -> None:
        self._memory_service = service

    # --------------------------------------------------------------- grants

    def grant(
        self,
        granting_profile_id: str,
        receiving_profile_id: str,
        memory_id: str,
    ) -> BridgeGrant:
        if granting_profile_id == receiving_profile_id:
            raise ValueError(
                "Cannot grant bridge access to the same profile"
            )
        grant_id = str(uuid.uuid4())
        now = _now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO bridge_grants (id, granting_profile_id, "
                "receiving_profile_id, memory_id, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    grant_id,
                    granting_profile_id,
                    receiving_profile_id,
                    memory_id,
                    now,
                ),
            )
            self._conn.commit()
        return BridgeGrant(
            id=grant_id,
            granting_profile_id=granting_profile_id,
            receiving_profile_id=receiving_profile_id,
            memory_id=memory_id,
            created_at=now,
        )

    def revoke(self, grant_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM bridge_grants WHERE id = ?", (grant_id,)
            )
            self._conn.commit()
            return cur.rowcount > 0

    def get_grant(self, grant_id: str) -> Optional[BridgeGrant]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM bridge_grants WHERE id = ?", (grant_id,)
            ).fetchone()
        return _grant_from_row(row) if row is not None else None

    def list_grants(
        self,
        granting_profile_id: Optional[str] = None,
        receiving_profile_id: Optional[str] = None,
    ) -> list[BridgeGrant]:
        with self._lock:
            sql = "SELECT * FROM bridge_grants WHERE 1=1"
            params: list[Any] = []
            if granting_profile_id is not None:
                sql += " AND granting_profile_id = ?"
                params.append(granting_profile_id)
            if receiving_profile_id is not None:
                sql += " AND receiving_profile_id = ?"
                params.append(receiving_profile_id)
            sql += " ORDER BY created_at ASC"
            rows = self._conn.execute(sql, params).fetchall()
        return [_grant_from_row(r) for r in rows]

    def _granted_memory_ids(
        self, granting_profile_id: str, receiving_profile_id: str
    ) -> set[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT memory_id FROM bridge_grants "
                "WHERE granting_profile_id = ? AND receiving_profile_id = ?",
                (granting_profile_id, receiving_profile_id),
            ).fetchall()
        return {r["memory_id"] for r in rows}

    # --------------------------------------------------------------- query

    def query(
        self,
        receiving_profile_id: str,
        granting_profile_id: str,
        query: str,
        limit: int = 5,
    ) -> list[MemoryRecord]:
        """Semantic query across granted memories from granting_profile.

        Returns memories owned by ``granting_profile_id`` that have an
        active grant to ``receiving_profile_id`` and match the semantic
        query. Logs the access to ``bridge_access_log``.
        """
        granted_ids = self._granted_memory_ids(
            granting_profile_id, receiving_profile_id
        )
        if not granted_ids:
            self._log_access(receiving_profile_id, granting_profile_id, query)
            return []
        if self._memory_service is None:
            self._log_access(receiving_profile_id, granting_profile_id, query)
            return []
        # Retrieve a generous pool of the granting profile's memories ranked
        # by semantic similarity, then keep only the explicitly granted ones.
        pool = self._memory_service.retrieve_memories(
            query=query,
            limit=max(limit * 10, 50),
            profile_id=granting_profile_id,
        )
        results = [r for r in pool if r.id in granted_ids][:limit]
        self._log_access(receiving_profile_id, granting_profile_id, query)
        return results

    # --------------------------------------------------------------- audit

    def _log_access(
        self,
        receiving_profile_id: str,
        granting_profile_id: str,
        query: str,
    ) -> None:
        now = _now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO bridge_access_log "
                "(receiving_profile_id, granting_profile_id, query, timestamp) "
                "VALUES (?, ?, ?, ?)",
                (receiving_profile_id, granting_profile_id, query, now),
            )
            self._conn.commit()

    def list_audit(
        self,
        receiving_profile_id: Optional[str] = None,
        granting_profile_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        with self._lock:
            sql = "SELECT * FROM bridge_access_log WHERE 1=1"
            params: list[Any] = []
            if receiving_profile_id is not None:
                sql += " AND receiving_profile_id = ?"
                params.append(receiving_profile_id)
            if granting_profile_id is not None:
                sql += " AND granting_profile_id = ?"
                params.append(granting_profile_id)
            sql += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = self._conn.execute(sql, params).fetchall()
        return [_audit_from_row(r) for r in rows]

    # ------------------------------------------------------- cascade helper

    def revoke_grants_for_profile(self, profile_id: str) -> int:
        """Delete all grants where the profile is granter or receiver.

        Called by the profiles router when a profile is deleted. Returns the
        number of grants removed.
        """
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM bridge_grants "
                "WHERE granting_profile_id = ? OR receiving_profile_id = ?",
                (profile_id, profile_id),
            )
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_bridge_service: Optional[BridgeService] = None
_singleton_lock = threading.Lock()


def get_bridge_service() -> BridgeService:
    global _bridge_service
    if _bridge_service is None:
        with _singleton_lock:
            if _bridge_service is None:
                _bridge_service = BridgeService()
    return _bridge_service


def set_bridge_service(svc: BridgeService) -> None:
    global _bridge_service
    with _singleton_lock:
        _bridge_service = svc


def reset_bridge_service() -> None:
    global _bridge_service
    with _singleton_lock:
        _bridge_service = None
