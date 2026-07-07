"""Session continuity manager: persists session metadata and generates a
contextual "Welcome back" message when the user returns after a gap.

Schema (SQLite, ``sessions`` table)::

    id            TEXT PRIMARY KEY
    profile_id    TEXT NOT NULL
    started_at    REAL NOT NULL   -- epoch seconds (time.time())
    ended_at      REAL            -- epoch seconds; NULL while session is open
    last_topic    TEXT
    last_task_id  TEXT

The temporal delta between sessions is computed via ``time.time()`` (epoch
seconds) so it survives process restarts. ``time.monotonic()`` is NOT used
because it has no meaning across restarts.

A welcome-back message is generated only when:
  1. A previous session exists for the profile (not the first run).
  2. The previous session has ended (``ended_at`` is set).
  3. The gap between ``ended_at`` and "now" exceeds ``WELCOME_THRESHOLD_SECONDS``
     (5 minutes by default).
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any


# Gap (in seconds) that must elapse between sessions before a welcome-back
# message is generated. 5 minutes = 300s.
WELCOME_THRESHOLD_SECONDS = 300

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    profile_id    TEXT NOT NULL,
    started_at    REAL NOT NULL,
    ended_at      REAL,
    last_topic    TEXT,
    last_task_id  TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_profile_ended
    ON sessions (profile_id, ended_at);
"""


def _default_db_path() -> str:
    env_dir = os.environ.get("GANESH_DATA_DIR")
    if env_dir:
        base = Path(env_dir)
    else:
        base = Path.home() / ".ganesh" / "data"
    base.mkdir(parents=True, exist_ok=True)
    return str(base / "continuity.db")


@dataclass
class Session:
    """A session continuity record."""

    id: str
    profile_id: str
    started_at: float
    ended_at: Optional[float]
    last_topic: Optional[str]
    last_task_id: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "profile_id": self.profile_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "last_topic": self.last_topic,
            "last_task_id": self.last_task_id,
        }


def _row_to_session(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        profile_id=row["profile_id"],
        started_at=float(row["started_at"]),
        ended_at=float(row["ended_at"]) if row["ended_at"] is not None else None,
        last_topic=row["last_topic"],
        last_task_id=row["last_task_id"],
    )


def _format_duration(seconds: float) -> str:
    """Format a duration in seconds as a human-readable phrase.

    Examples: "5 minutes", "2 hours", "3 days", "45 seconds".
    Uses the largest whole unit that fits.
    """
    if seconds < 0:
        seconds = 0.0
    if seconds < 60:
        n = max(1, int(round(seconds)))
        return f"{n} second{'s' if n != 1 else ''}"
    if seconds < 3600:
        n = max(1, int(round(seconds / 60)))
        return f"{n} minute{'s' if n != 1 else ''}"
    if seconds < 86400:
        n = max(1, int(round(seconds / 3600)))
        return f"{n} hour{'s' if n != 1 else ''}"
    n = max(1, int(round(seconds / 86400)))
    return f"{n} day{'s' if n != 1 else ''}"


class ContinuityService:
    """SQLite-backed session continuity manager.

    Thread-safe via ``threading.RLock``. Uses ``check_same_thread=False`` so
    FastAPI's threadpool can call into the same connection safely (SQLite
    serialises writes internally).
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        threshold_seconds: float = WELCOME_THRESHOLD_SECONDS,
    ) -> None:
        self._db_path: str = db_path or _default_db_path()
        self._threshold: float = threshold_seconds
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection = sqlite3.connect(
            self._db_path, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------- sessions

    def start_session(self, profile_id: str) -> Session:
        """Create a new session record for ``profile_id`` and return it.

        ``started_at`` is captured via ``time.time()`` (epoch seconds) so the
        delta survives process restarts.
        """
        if not profile_id:
            raise ValueError("profile_id must not be empty")
        session_id = str(uuid.uuid4())
        started = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions (id, profile_id, started_at, ended_at, "
                "last_topic, last_task_id) VALUES (?, ?, ?, NULL, NULL, NULL)",
                (session_id, profile_id, started),
            )
            self._conn.commit()
        return Session(
            id=session_id,
            profile_id=profile_id,
            started_at=started,
            ended_at=None,
            last_topic=None,
            last_task_id=None,
        )

    def end_session(
        self,
        session_id: str,
        last_topic: Optional[str] = None,
        last_task_id: Optional[str] = None,
    ) -> Optional[Session]:
        """Mark a session as ended, recording the last topic / task id.

        Returns the updated session, or ``None`` if no session with that id
        exists. ``ended_at`` is captured via ``time.time()``.
        """
        ended = time.time()
        with self._lock:
            cur = self._conn.execute(
                "UPDATE sessions SET ended_at = ?, last_topic = ?, "
                "last_task_id = ? WHERE id = ?",
                (ended, last_topic, last_task_id, session_id),
            )
            self._conn.commit()
            if cur.rowcount == 0:
                return None
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return _row_to_session(row) if row is not None else None

    def get_last_session(self, profile_id: str) -> Optional[Session]:
        """Return the most recently ended session for ``profile_id``.

        Only sessions with a non-null ``ended_at`` are considered. Returns
        ``None`` if the profile has no ended sessions.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE profile_id = ? AND ended_at IS NOT NULL "
                "ORDER BY ended_at DESC LIMIT 1",
                (profile_id,),
            ).fetchone()
        return _row_to_session(row) if row is not None else None

    def get_open_session(self, profile_id: str) -> Optional[Session]:
        """Return the most recent open (non-ended) session for ``profile_id``."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE profile_id = ? AND ended_at IS NULL "
                "ORDER BY started_at DESC LIMIT 1",
                (profile_id,),
            ).fetchone()
        return _row_to_session(row) if row is not None else None

    def get_session(self, session_id: str) -> Optional[Session]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return _row_to_session(row) if row is not None else None

    # ------------------------------------------------------- welcome-back

    def generate_welcome_back(
        self,
        profile_id: str,
        now: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        """Return a welcome-back payload, or ``None`` if no message applies.

        Returns ``None`` when:
          - The profile has no previous ended session (first run).
          - The gap since the last session ended is <= the threshold.

        Otherwise returns a dict::

            {
                "message": "Welcome back! It's been {duration}. You were "
                           "working on {last_topic}. Want to continue?",
                "duration_seconds": float,
                "duration_phrase": str,
                "last_topic": str | None,
                "last_task_id": str | None,
                "last_session_id": str,
            }

        ``now`` is injectable for tests; defaults to ``time.time()`` (epoch
        seconds). The delta is computed via ``time.time()`` so it survives
        process restarts — ``time.monotonic()`` is NOT used because it has
        no meaning across reboots.
        """
        last = self.get_last_session(profile_id)
        if last is None or last.ended_at is None:
            return None
        current = now if now is not None else time.time()
        delta = current - last.ended_at
        if delta <= self._threshold:
            return None
        duration = _format_duration(delta)
        topic = last.last_topic or "your last task"
        message = (
            f"Welcome back! It's been {duration}. "
            f"You were working on {topic}. Want to continue?"
        )
        return {
            "message": message,
            "duration_seconds": delta,
            "duration_phrase": duration,
            "last_topic": last.last_topic,
            "last_task_id": last.last_task_id,
            "last_session_id": last.id,
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ---------------------------------------------------------------------------
# Process-wide singleton (mirrors profile_manager / task_manager pattern)
# ---------------------------------------------------------------------------

_service: Optional[ContinuityService] = None
_singleton_lock = threading.Lock()


def get_continuity_service() -> ContinuityService:
    global _service
    if _service is None:
        with _singleton_lock:
            if _service is None:
                _service = ContinuityService()
    return _service


def set_continuity_service(svc: ContinuityService) -> None:
    """Inject a service instance (used by tests to wire mocks)."""
    global _service
    with _singleton_lock:
        _service = svc


def reset_continuity_service() -> None:
    """Clear the singleton (used by tests)."""
    global _service
    with _singleton_lock:
        _service = None
