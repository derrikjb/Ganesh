"""Async task manager with SQLite status store for background operations.

Task lifecycle::

    PENDING ──start──► RUNNING ──success──► COMPLETED
                       RUNNING ──exception──► FAILED
                       RUNNING ──cancel────►  CANCELLED
                       RUNNING ──crash─────►  INTERRUPTED  (recovery on startup)

Task functions are registered via :meth:`TaskManager.register_task_type` and
must be async callables with the signature::

    async def fn(task_id: str, input: dict, ctx: TaskContext) -> Any

The :class:`TaskContext` exposes ``report_progress`` which updates the SQLite
row and pushes the update to any active SSE subscribers.

SQLite schema (table ``tasks``)::

    id             TEXT PRIMARY KEY
    goal           TEXT
    status         TEXT   -- pending|running|completed|failed|cancelled|interrupted
    current_action TEXT
    result_json    TEXT   -- JSON-encoded result or error
    started_at     TEXT   -- ISO 8601 UTC
    completed_at   TEXT   -- ISO 8601 UTC, NULL while in flight
    task_type      TEXT

The DB path defaults to ``$GANESH_DATA_DIR/ganesh.db`` or
``~/.ganesh/ganesh.db``. Tests pass an explicit path (often a tmpdir).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums and data types
# ---------------------------------------------------------------------------


class TaskStatus(str, Enum):
    """Lifecycle states for a background task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


# A registered task function: async (task_id, input, ctx) -> Any.
TaskFn = Callable[[str, dict[str, Any], "TaskContext"], Awaitable[Any]]


# ---------------------------------------------------------------------------
# TaskContext — passed into each task function
# ---------------------------------------------------------------------------


@dataclass
class TaskContext:
    """Runtime context handed to a task function.

    Holds a back-reference to the owning :class:`TaskManager` and the task id
    so the task can report progress without needing direct DB access.
    """

    manager: "TaskManager"
    task_id: str

    async def report_progress(
        self,
        action: str,
        progress: Optional[float] = None,
    ) -> None:
        """Update the task's ``current_action`` and notify SSE subscribers."""
        extra: dict[str, Any] = {"action": action}
        if progress is not None:
            extra["progress"] = progress
        await self.manager._publish(self.task_id, extra)


# ---------------------------------------------------------------------------
# TaskManager
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id             TEXT PRIMARY KEY,
    goal           TEXT NOT NULL,
    status         TEXT NOT NULL,
    current_action TEXT,
    result_json    TEXT,
    started_at     TEXT NOT NULL,
    completed_at   TEXT,
    task_type      TEXT NOT NULL
);
"""


def _default_db_path() -> str:
    env_dir = os.environ.get("GANESH_DATA_DIR")
    if env_dir:
        base = Path(env_dir)
    else:
        base = Path.home() / ".ganesh"
    base.mkdir(parents=True, exist_ok=True)
    return str(base / "ganesh.db")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskManager:
    """Async task manager backed by SQLite.

    Thread-safe for registration and DB queries (which acquire ``_lock``).
    The in-memory ``asyncio.Task`` map and subscriber queues are owned by
    the event loop running ``start_task`` / ``get_task_stream``.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path: str = db_path or _default_db_path()
        self._lock = threading.RLock()
        # task_id -> asyncio.Task wrapping _run_task
        self._async_tasks: dict[str, asyncio.Task[Any]] = {}
        # task_id -> list[asyncio.Queue] for SSE subscribers
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        # task_type -> async callable
        self._registry: dict[str, TaskFn] = {}
        self._init_db()
        self._recover_orphaned()

    # ------------------------------------------------------------------ DB

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._conn() as conn:
                conn.executescript(_SCHEMA)
                conn.commit()

    def _recover_orphaned(self) -> None:
        """Mark any RUNNING/PENDING tasks as INTERRUPTED on startup.

        Called from ``__init__`` so a crashed sidecar's in-flight tasks are
        not left stuck forever when the process restarts.
        """
        with self._lock:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT id FROM tasks WHERE status IN (?, ?)",
                    (TaskStatus.RUNNING.value, TaskStatus.PENDING.value),
                ).fetchall()
                if not rows:
                    return
                now = _now_iso()
                conn.execute(
                    "UPDATE tasks SET status = ?, completed_at = ? "
                    "WHERE status IN (?, ?)",
                    (
                        TaskStatus.INTERRUPTED.value,
                        now,
                        TaskStatus.RUNNING.value,
                        TaskStatus.PENDING.value,
                    ),
                )
                conn.commit()
            orphan_ids = [r["id"] for r in rows]
            logger.info("Recovered %d orphaned task(s): %s", len(orphan_ids), orphan_ids)

    # ----------------------------------------------------------- registry

    def register_task_type(self, task_type: str, fn: TaskFn) -> None:
        with self._lock:
            self._registry[task_type] = fn

    def get_registered_types(self) -> list[str]:
        with self._lock:
            return list(self._registry.keys())

    # ----------------------------------------------------------- lifecycle

    async def start_task(
        self,
        goal: str,
        task_type: str,
        input: dict[str, Any],
    ) -> str:
        """Create a task row (PENDING) and schedule the async runner.

        Returns the new task id. Raises ``KeyError`` if ``task_type`` is not
        registered.
        """
        with self._lock:
            if task_type not in self._registry:
                raise KeyError(f"Unknown task type: {task_type}")
            task_id = str(uuid.uuid4())
            started_at = _now_iso()
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO tasks "
                    "(id, goal, status, current_action, result_json, "
                    " started_at, completed_at, task_type) "
                    "VALUES (?, ?, ?, ?, NULL, ?, NULL, ?)",
                    (
                        task_id,
                        goal,
                        TaskStatus.PENDING.value,
                        "",
                        started_at,
                        task_type,
                    ),
                )
                conn.commit()
            self._subscribers.setdefault(task_id, [])

        loop = asyncio.get_running_loop()
        asyncio_task = loop.create_task(self._run_task(task_id, task_type, input))
        self._async_tasks[task_id] = asyncio_task
        return task_id

    async def _run_task(
        self,
        task_id: str,
        task_type: str,
        input: dict[str, Any],
    ) -> None:
        fn = self._registry[task_type]
        self._set_status(task_id, TaskStatus.RUNNING, current_action="starting")
        await self._publish(task_id, {"action": "starting", "status": "running"})
        ctx = TaskContext(manager=self, task_id=task_id)
        try:
            result = await fn(task_id, input, ctx)
        except asyncio.CancelledError:
            self._set_status(
                task_id,
                TaskStatus.CANCELLED,
                current_action="cancelled",
                result=None,
            )
            await self._publish(
                task_id, {"status": "cancelled", "action": "cancelled"}
            )
            self._drop_task(task_id)
            raise
        except Exception as exc:
            err = {"error": str(exc), "type": type(exc).__name__}
            self._set_status(
                task_id,
                TaskStatus.FAILED,
                current_action="failed",
                result=err,
            )
            await self._publish(
                task_id, {"status": "failed", "action": "failed", "error": err}
            )
            logger.exception("Task %s failed", task_id)
            self._drop_task(task_id)
            return
        self._set_status(
            task_id,
            TaskStatus.COMPLETED,
            current_action="completed",
            result={"result": result} if not isinstance(result, dict) else result,
        )
        await self._publish(
            task_id,
            {"status": "completed", "action": "completed", "result": result},
        )
        self._drop_task(task_id)

    def _set_status(
        self,
        task_id: str,
        status: TaskStatus,
        current_action: Optional[str] = None,
        result: Optional[Any] = None,
    ) -> None:
        with self._lock:
            now = _now_iso()
            completed_at: Optional[str] = now if status in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
                TaskStatus.INTERRUPTED,
            ) else None
            result_json = json.dumps(result) if result is not None else None
            with self._conn() as conn:
                conn.execute(
                    "UPDATE tasks SET status = ?, current_action = ?, "
                    "result_json = ?, completed_at = ? WHERE id = ?",
                    (
                        status.value,
                        current_action or "",
                        result_json,
                        completed_at,
                        task_id,
                    ),
                )
                conn.commit()

    def _drop_task(self, task_id: str) -> None:
        self._async_tasks.pop(task_id, None)
        # Close subscriber queues: push a sentinel so streams terminate.
        for q in self._subscribers.pop(task_id, []):
            try:
                q.put_nowait({"_done": True})
            except asyncio.QueueFull:
                pass

    def _abort_in_memory(self, task_id: str) -> None:
        """Cancel the asyncio task without touching the DB row.

        Used by tests to simulate a crash that leaves the DB row stuck at
        ``running`` so that a subsequent :class:`TaskManager` startup can
        demonstrate orphaned recovery.
        """
        t = self._async_tasks.pop(task_id, None)
        if t is not None and not t.done():
            t.cancel()

    # ----------------------------------------------------------- queries

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT * FROM tasks WHERE id = ?", (task_id,)
                ).fetchone()
            if row is None:
                return None
            return _row_to_dict(row)

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM tasks ORDER BY started_at DESC"
                ).fetchall()
            return [_row_to_dict(r) for r in rows]

    # ----------------------------------------------------------- cancel

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task. Returns True if a task was cancelled."""
        t = self._async_tasks.get(task_id)
        if t is None or t.done():
            # Already finished or unknown — reflect that in the DB if needed.
            info = self.get_task(task_id)
            if info is None:
                return False
            if info["status"] in (
                TaskStatus.RUNNING.value,
                TaskStatus.PENDING.value,
            ):
                self._set_status(
                    task_id, TaskStatus.CANCELLED, current_action="cancelled"
                )
                await self._publish(
                    task_id, {"status": "cancelled", "action": "cancelled"}
                )
                return True
            return False
        t.cancel()
        # Let _run_task's CancelledError handler update the DB.
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass
        return True

    # ----------------------------------------------------------- SSE stream

    async def get_task_stream(
        self, task_id: str
    ) -> AsyncIterator[dict[str, Any]]:
        """Async generator yielding progress-update dicts for SSE.

        Terminates when the task reaches a terminal state (completed, failed,
        cancelled, interrupted) or when the task id is unknown.
        """
        info = self.get_task(task_id)
        if info is None:
            return
        # If already terminal, yield the final state once and stop.
        terminal = {
            TaskStatus.COMPLETED.value,
            TaskStatus.FAILED.value,
            TaskStatus.CANCELLED.value,
            TaskStatus.INTERRUPTED.value,
        }
        if info["status"] in terminal:
            yield {"status": info["status"], "action": info["current_action"]}
            return

        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        with self._lock:
            self._subscribers.setdefault(task_id, []).append(q)
        try:
            while True:
                update = await q.get()
                if update.get("_done"):
                    return
                yield update
                if update.get("status") in terminal:
                    return
        finally:
            with self._lock:
                subs = self._subscribers.get(task_id)
                if subs and q in subs:
                    subs.remove(q)

    async def _publish(self, task_id: str, update: dict[str, Any]) -> None:
        """Broadcast a progress update to all SSE subscribers for a task."""
        with self._lock:
            subs = list(self._subscribers.get(task_id, []))
        for q in subs:
            try:
                q.put_nowait(update)
            except asyncio.QueueFull:
                pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    result_json = d.get("result_json")
    if result_json:
        try:
            d["result"] = json.loads(result_json)
        except (json.JSONDecodeError, TypeError):
            d["result"] = None
    else:
        d["result"] = None
    return d


# ---------------------------------------------------------------------------
# Process-wide singleton (mirrors voice_activation / model_manager pattern)
# ---------------------------------------------------------------------------


_task_manager: Optional[TaskManager] = None
_singleton_lock = threading.Lock()


def get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        with _singleton_lock:
            if _task_manager is None:
                _task_manager = TaskManager()
    return _task_manager


def reset_task_manager() -> None:
    """Clear the singleton (used by tests)."""
    global _task_manager
    with _singleton_lock:
        _task_manager = None


def set_task_manager(mgr: TaskManager) -> None:
    """Inject a manager instance (used by tests to wire mocks)."""
    global _task_manager
    with _singleton_lock:
        _task_manager = mgr
