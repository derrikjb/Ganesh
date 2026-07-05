"""Tests for the async task manager with SQLite status store.

Covers:
    - test_start_task        — task starts and returns an id
    - test_get_status        — status is queryable after start
    - test_cancel_task       — cancel stops a running task
    - test_task_persistence   — task row survives a sidecar restart
                               (simulated by re-opening the DB)
    - test_orphaned_recovery  — RUNNING tasks are marked INTERRUPTED on startup

All task functions are mocked with short ``asyncio.sleep`` calls so no real
long-running work is performed.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from ganesh_backend.services.task_manager import (  # noqa: E402
    TaskContext,
    TaskManager,
    TaskStatus,
)


# ---------------------------------------------------------------------------
# Mocked task functions
# ---------------------------------------------------------------------------


async def _slow_task(task_id: str, input: dict[str, Any], ctx: TaskContext) -> dict[str, Any]:
    """A task that sleeps long enough to be observable, reporting progress."""
    await ctx.report_progress("starting")
    for i in range(3):
        await asyncio.sleep(0.05)
        await ctx.report_progress(f"step {i + 1}", progress=(i + 1) * 33)
    return {"ok": True, "echo": input.get("echo")}


async def _quick_task(task_id: str, input: dict[str, Any], ctx: TaskContext) -> dict[str, Any]:
    """A task that completes almost immediately."""
    await ctx.report_progress("done")
    return {"ok": True}


async def _hanging_task(task_id: str, input: dict[str, Any], ctx: TaskContext) -> dict[str, Any]:
    """A task that sleeps indefinitely until cancelled."""
    await ctx.report_progress("starting")
    try:
        await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await ctx.report_progress("cancelled")
        raise
    return {"ok": True}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manager(tmp_path: Path) -> TaskManager:
    db_path = str(tmp_path / "ganesh.db")
    mgr = TaskManager(db_path=db_path)
    mgr.register_task_type("slow", _slow_task)
    mgr.register_task_type("quick", _quick_task)
    mgr.register_task_type("hanging", _hanging_task)
    return mgr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_task(manager: TaskManager) -> None:
    task_id = await manager.start_task(
        goal="do something", task_type="quick", input={"echo": "hi"}
    )
    assert isinstance(task_id, str)
    assert len(task_id) > 0
    # Allow the task to run to completion.
    await asyncio.sleep(0.2)
    status = manager.get_task(task_id)
    assert status is not None
    assert status["status"] == TaskStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_get_status(manager: TaskManager) -> None:
    task_id = await manager.start_task(
        goal="queryable task", task_type="quick", input={}
    )
    info = manager.get_task(task_id)
    assert info is not None
    assert info["id"] == task_id
    assert info["goal"] == "queryable task"
    assert info["task_type"] == "quick"
    assert info["status"] in (
        TaskStatus.PENDING.value,
        TaskStatus.RUNNING.value,
        TaskStatus.COMPLETED.value,
    )
    assert info["started_at"]
    # Wait for completion so the manager's background task isn't pending at
    # teardown.
    await asyncio.sleep(0.2)
    final = manager.get_task(task_id)
    assert final is not None
    assert final["status"] == TaskStatus.COMPLETED.value
    assert final["completed_at"]


@pytest.mark.asyncio
async def test_cancel_task(manager: TaskManager) -> None:
    task_id = await manager.start_task(
        goal="cancel me", task_type="hanging", input={}
    )
    # Give the task a moment to enter RUNNING.
    await asyncio.sleep(0.05)
    cancelled = await manager.cancel_task(task_id)
    assert cancelled is True
    info = manager.get_task(task_id)
    assert info is not None
    assert info["status"] == TaskStatus.CANCELLED.value
    assert info["completed_at"]


@pytest.mark.asyncio
async def test_task_persistence(tmp_path: Path) -> None:
    db_path = str(tmp_path / "ganesh.db")
    mgr1 = TaskManager(db_path=db_path)
    mgr1.register_task_type("quick", _quick_task)
    task_id = await mgr1.start_task(goal="persist me", task_type="quick", input={})
    # Wait for completion.
    await asyncio.sleep(0.2)
    info = mgr1.get_task(task_id)
    assert info is not None
    assert info["status"] == TaskStatus.COMPLETED.value
    # Simulate a sidecar restart: discard the manager and create a new one
    # pointing at the same DB file. The task row must still be present.
    mgr2 = TaskManager(db_path=db_path)
    info2 = mgr2.get_task(task_id)
    assert info2 is not None
    assert info2["id"] == task_id
    assert info2["goal"] == "persist me"
    assert info2["status"] == TaskStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_orphaned_recovery(tmp_path: Path) -> None:
    db_path = str(tmp_path / "ganesh.db")
    # First instance: insert a task and force its DB row to "running" so it
    # looks orphaned (as if the sidecar died mid-task).
    mgr1 = TaskManager(db_path=db_path)
    mgr1.register_task_type("hanging", _hanging_task)
    task_id = await mgr1.start_task(goal="orphan", task_type="hanging", input={})
    await asyncio.sleep(0.05)
    # Simulate a crash: cancel the asyncio task in-memory WITHOUT updating
    # the DB, leaving the row stuck at "running".
    mgr1._abort_in_memory(task_id)  # type: ignore[attr-defined]
    row = mgr1.get_task(task_id)
    assert row is not None
    assert row["status"] == TaskStatus.RUNNING.value

    # New manager on startup must mark the orphaned RUNNING task as INTERRUPTED.
    mgr2 = TaskManager(db_path=db_path)
    recovered = mgr2.get_task(task_id)
    assert recovered is not None
    assert recovered["status"] == TaskStatus.INTERRUPTED.value
    assert recovered["completed_at"]
