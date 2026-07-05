"""Profile manager: multi-user profile CRUD with SQLite persistence.

Each profile is an isolated memory scope. The active profile is tracked in a
singleton row (``active_profile`` table) so the memory router can scope all
store/retrieve operations by ``profile_id`` without the caller passing it
explicitly.

Schema (SQLite, ``profiles`` table)::

    id          TEXT PRIMARY KEY
    name        TEXT NOT NULL
    description TEXT
    color       TEXT
    created_at  TEXT NOT NULL
    updated_at  TEXT NOT NULL

The ``active_profile`` table has a single row (id=1) pointing at the active
profile. On first profile creation, that profile is auto-activated. At least
one profile always exists once created (deleting the last profile is refused
with a 400).
"""
from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol


_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    color       TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS active_profile (
    id          INTEGER PRIMARY KEY DEFAULT 1,
    profile_id  TEXT NOT NULL
);
"""


def _default_db_path() -> str:
    env_dir = os.environ.get("GANESH_DATA_DIR")
    if env_dir:
        base = Path(env_dir)
    else:
        base = Path.home() / ".ganesh"
    base.mkdir(parents=True, exist_ok=True)
    return str(base / "profiles.db")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Profile:
    """A user profile record."""

    id: str
    name: str
    description: Optional[str]
    color: Optional[str]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "color": self.color,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _row_to_profile(row: sqlite3.Row) -> Profile:
    return Profile(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        color=row["color"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class MemoryDeleterProtocol(Protocol):
    """Minimal interface for cascade-deleting a profile's memories."""

    def delete_memory(self, memory_id: str, profile_id: Optional[str] = None) -> bool: ...

    def list_memories(self, profile_id: Optional[str] = None) -> list[Any]: ...


class BridgeCascadeProtocol(Protocol):
    """Minimal interface for cascade-deleting bridge grants referencing a profile."""

    def revoke_grants_for_profile(self, profile_id: str) -> int: ...


class ProfileManager:
    """SQLite-backed profile store with active-profile tracking.

    Thread-safe via ``threading.RLock``. Uses ``check_same_thread=False`` so
    FastAPI's threadpool can call into the same connection safely (SQLite
    serialises writes internally).
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path: str = db_path or _default_db_path()
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection = sqlite3.connect(
            self._db_path, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._memory_deleter: Optional[MemoryDeleterProtocol] = None
        self._bridge_cascade: Optional[BridgeCascadeProtocol] = None
        self._init_db()

    def set_memory_deleter(self, deleter: MemoryDeleterProtocol) -> None:
        with self._lock:
            self._memory_deleter = deleter

    def set_bridge_cascade(self, cascade: BridgeCascadeProtocol) -> None:
        with self._lock:
            self._bridge_cascade = cascade

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------------ CRUD

    def create_profile(
        self,
        name: str,
        description: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Profile:
        if not name or not name.strip():
            raise ValueError("Profile name must not be empty")
        profile_id = str(uuid.uuid4())
        now = _now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO profiles (id, name, description, color, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (profile_id, name.strip(), description, color, now, now),
            )
            self._conn.commit()
            # Auto-activate if this is the first profile.
            if self._get_active_id_unlocked() is None:
                self._set_active_id_unlocked(profile_id)
        return self.get_profile(profile_id)  # type: ignore[return-value]

    def list_profiles(self) -> list[Profile]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM profiles ORDER BY created_at ASC"
            ).fetchall()
        return [_row_to_profile(r) for r in rows]

    def get_profile(self, profile_id: str) -> Optional[Profile]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM profiles WHERE id = ?", (profile_id,)
            ).fetchone()
        return _row_to_profile(row) if row is not None else None

    def update_profile(
        self,
        profile_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Optional[Profile]:
        existing = self.get_profile(profile_id)
        if existing is None:
            return None
        new_name = name.strip() if name is not None else existing.name
        if not new_name:
            raise ValueError("Profile name must not be empty")
        new_desc = description if description is not None else existing.description
        new_color = color if color is not None else existing.color
        now = _now_iso()
        with self._lock:
            self._conn.execute(
                "UPDATE profiles SET name = ?, description = ?, color = ?, "
                "updated_at = ? WHERE id = ?",
                (new_name, new_desc, new_color, now, profile_id),
            )
            self._conn.commit()
        return self.get_profile(profile_id)

    def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile, cascading to its memories and bridge grants.

        Refuses if it is the last remaining profile. If the deleted profile
        was active, the first remaining profile is re-activated. Cascade
        hooks (memory deleter, bridge cascade) are invoked best-effort before
        the profile row is removed.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM profiles WHERE id = ?", (profile_id,)
            ).fetchone()
            if row is None:
                return False
            count = self._conn.execute(
                "SELECT COUNT(*) AS n FROM profiles"
            ).fetchone()["n"]
            if count <= 1:
                raise ValueError("Cannot delete the last remaining profile")
            active_id = self._get_active_id_unlocked()

            # Cascade: delete the profile's memories via the memory service.
            if self._memory_deleter is not None:
                try:
                    for mem in self._memory_deleter.list_memories(profile_id=profile_id):
                        self._memory_deleter.delete_memory(mem.id, profile_id=profile_id)
                except Exception:
                    pass

            # Cascade: revoke bridge grants referencing this profile.
            if self._bridge_cascade is not None:
                try:
                    self._bridge_cascade.revoke_grants_for_profile(profile_id)
                except Exception:
                    pass

            self._conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
            self._conn.commit()
            if active_id == profile_id:
                # Re-activate the first remaining profile.
                other = self._conn.execute(
                    "SELECT id FROM profiles ORDER BY created_at ASC LIMIT 1"
                ).fetchone()
                if other is not None:
                    self._set_active_id_unlocked(other["id"])
        return True

    # ------------------------------------------------------- active profile

    def activate_profile(self, profile_id: str) -> Optional[Profile]:
        profile = self.get_profile(profile_id)
        if profile is None:
            return None
        with self._lock:
            self._set_active_id_unlocked(profile_id)
        return profile

    def get_active_profile(self) -> Optional[Profile]:
        with self._lock:
            active_id = self._get_active_id_unlocked()
        if active_id is None:
            return None
        return self.get_profile(active_id)

    def get_active_profile_id(self) -> Optional[str]:
        with self._lock:
            return self._get_active_id_unlocked()

    # ----------------------------------------------------- internal helpers

    def _get_active_id_unlocked(self) -> Optional[str]:
        row = self._conn.execute(
            "SELECT profile_id FROM active_profile WHERE id = 1"
        ).fetchone()
        return row["profile_id"] if row is not None else None

    def _set_active_id_unlocked(self, profile_id: str) -> None:
        self._conn.execute(
            "INSERT INTO active_profile (id, profile_id) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET profile_id = excluded.profile_id",
            (profile_id,),
        )
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ---------------------------------------------------------------------------
# Process-wide singleton (mirrors task_manager / memory / personality pattern)
# ---------------------------------------------------------------------------

_profile_manager: Optional[ProfileManager] = None
_singleton_lock = threading.Lock()


def get_profile_manager() -> ProfileManager:
    global _profile_manager
    if _profile_manager is None:
        with _singleton_lock:
            if _profile_manager is None:
                _profile_manager = ProfileManager()
    return _profile_manager


def set_profile_manager(mgr: ProfileManager) -> None:
    """Inject a manager instance (used by tests to wire mocks)."""
    global _profile_manager
    with _singleton_lock:
        _profile_manager = mgr


def reset_profile_manager() -> None:
    """Clear the singleton (used by tests)."""
    global _profile_manager
    with _singleton_lock:
        _profile_manager = None
