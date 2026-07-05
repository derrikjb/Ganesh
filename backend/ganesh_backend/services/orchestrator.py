"""Main-agent orchestrator — spawns sub-agents and queries their status.

The :class:`Orchestrator` is the thin coordination layer between the
chat flow and the :class:`SubAgentRunner` / :class:`TaskManager`. It
exposes a small surface that the FastAPI ``agents`` router calls:

    * :meth:`spawn_sub_agent`           — schedule a sub-agent, return id
    * :meth:`query_sub_agent_status`    — non-blocking status summary
    * :meth:`get_sub_agent_result`      — fetch result when complete
    * :meth:`list_active_sub_agents`    — list running/pending sub-agents
    * :meth:`cancel_sub_agent`          — cancel a running sub-agent

When a user asks the main agent about a task, the orchestrator queries
the TaskManager status store (a non-blocking SQLite read) and returns a
summary. When a sub-agent completes, its result is fetched and injected
into the main agent's LLM context as a system message.
"""
from __future__ import annotations

from typing import Any, Optional

from ganesh_backend.services.sub_agent import SubAgentRunner
from ganesh_backend.services.task_manager import (
    TaskManager,
    TaskStatus,
)

# Statuses that count as "active" (in flight) for list_active_sub_agents.
_ACTIVE_STATUSES: tuple[str, ...] = (
    TaskStatus.PENDING.value,
    TaskStatus.RUNNING.value,
)

# Statuses that count as "terminal" for get_sub_agent_result.
_TERMINAL_STATUSES: tuple[str, ...] = (
    TaskStatus.COMPLETED.value,
    TaskStatus.FAILED.value,
    TaskStatus.CANCELLED.value,
    TaskStatus.INTERRUPTED.value,
)


class Orchestrator:
    """Coordinates spawning and querying sub-agents.

    The orchestrator holds a :class:`SubAgentRunner` (which owns the
    TaskManager registration) and forwards spawn calls to it. Status
    and result queries go straight to the TaskManager's SQLite store,
    so they are non-blocking and safe to call from the chat flow.
    """

    def __init__(
        self,
        task_manager: Optional[TaskManager] = None,
        runner: Optional[SubAgentRunner] = None,
    ) -> None:
        if task_manager is None:
            from ganesh_backend.services.task_manager import get_task_manager

            task_manager = get_task_manager()
        self.task_manager = task_manager
        self.runner = runner or SubAgentRunner(self.task_manager)

    # ----------------------------------------------------------- spawn

    async def spawn_sub_agent(
        self,
        goal: str,
        task_type: str,
        input: dict[str, Any],
        tools: Optional[list[str]] = None,
    ) -> str:
        """Spawn a sub-agent and return its task id immediately."""
        return await self.runner.run_sub_agent(
            goal=goal, task_type=task_type, input=input, tools=tools
        )

    # ----------------------------------------------------------- query

    def query_sub_agent_status(self, task_id: str) -> Optional[dict[str, Any]]:
        """Non-blocking status summary for a sub-agent.

        Returns ``None`` if the task id is unknown. Otherwise a dict
        with ``task_id``, ``goal``, ``status``, ``current_action`` and
        ``progress`` (when available).
        """
        row = self.task_manager.get_task(task_id)
        if row is None:
            return None
        return {
            "task_id": row["id"],
            "goal": row["goal"],
            "status": row["status"],
            "current_action": row.get("current_action") or "",
            "task_type": row.get("task_type") or "",
            "started_at": row.get("started_at") or "",
            "completed_at": row.get("completed_at"),
        }

    def get_sub_agent_result(
        self, task_id: str
    ) -> Optional[dict[str, Any]]:
        """Fetch a completed sub-agent's result.

        Returns ``None`` if the task is unknown or not yet in a terminal
        state. For completed tasks the result dict (containing
        ``content``, ``goal``, ``task_type`` ...) is returned. For
        failed / cancelled / interrupted tasks the stored error / null
        result is returned so the caller can surface the failure.
        """
        row = self.task_manager.get_task(task_id)
        if row is None:
            return None
        if row["status"] not in _TERMINAL_STATUSES:
            return None
        return {
            "task_id": row["id"],
            "goal": row["goal"],
            "status": row["status"],
            "result": row.get("result"),
            "completed_at": row.get("completed_at"),
        }

    def list_active_sub_agents(self) -> list[dict[str, Any]]:
        """List all pending/running sub-agents (non-blocking)."""
        rows = self.task_manager.list_tasks()
        active = [r for r in rows if r["status"] in _ACTIVE_STATUSES]
        return [
            {
                "task_id": r["id"],
                "goal": r["goal"],
                "status": r["status"],
                "current_action": r.get("current_action") or "",
                "task_type": r.get("task_type") or "",
                "started_at": r.get("started_at") or "",
            }
            for r in active
        ]

    def list_all_sub_agents(self) -> list[dict[str, Any]]:
        """List every sub-agent task row (active + terminal)."""
        rows = self.task_manager.list_tasks()
        return [
            {
                "task_id": r["id"],
                "goal": r["goal"],
                "status": r["status"],
                "current_action": r.get("current_action") or "",
                "task_type": r.get("task_type") or "",
                "started_at": r.get("started_at") or "",
                "completed_at": r.get("completed_at"),
            }
            for r in rows
        ]

    async def cancel_sub_agent(self, task_id: str) -> bool:
        """Cancel a running sub-agent. Returns True if a task was cancelled."""
        return await self.task_manager.cancel_task(task_id)

    # ----------------------------------------------------------- context

    def build_result_context_message(
        self, task_id: str
    ) -> Optional[dict[str, str]]:
        """Build a system message injecting a completed sub-agent's result
        into the main agent's LLM context.

        Returns ``None`` if the task is unknown or not complete. The
        returned message has ``role == "system"`` and a ``content``
        string summarising the sub-agent's goal and output, suitable
        for appending to the main chat's message list.
        """
        info = self.get_sub_agent_result(task_id)
        if info is None:
            return None
        result = info.get("result") or {}
        content = result.get("content") if isinstance(result, dict) else None
        if content is None:
            # Failed / cancelled task — surface the failure instead.
            content = f"[Sub-agent {task_id} ended in state {info['status']}]"
        body = (
            f"Sub-agent result (task_id={task_id}, goal={info['goal']}):\n"
            f"{content}"
        )
        return {"role": "system", "content": body}


# ---------------------------------------------------------------------------
# Process-wide singleton
# ---------------------------------------------------------------------------

_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


def reset_orchestrator() -> None:
    global _orchestrator
    _orchestrator = None
