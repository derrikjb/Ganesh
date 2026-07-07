"""Sub-agent runner — executes a sub-agent as an async TaskManager task.

A *sub-agent* is a lightweight agent spawned by the main orchestrator to
pursue a narrow goal in the background. Each sub-agent:

    * Has a ``goal`` (natural-language objective).
    * Has a ``task_type`` (user-facing label, e.g. ``"research"``).
    * Receives an ``input`` dict (payload from the main agent / user).
    * Is restricted to a subset of the main agent's ``tools`` (by name).
    * Shares the main agent's LLM context (model + API key).

Sub-agents are scheduled via :class:`TaskManager` so their lifecycle
(pending → running → completed/failed/cancelled) is persisted in the
SQLite status store and queryable non-blocking. Progress is reported
through :meth:`TaskContext.report_progress` so SSE subscribers and the
orchestrator's status queries see live ``current_action`` updates.

The completed result is stored in the task row's ``result_json`` column
and is retrieved by the orchestrator via :meth:`TaskManager.get_task`.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from ganesh_backend.services import llm as llm_service
from ganesh_backend.services.task_manager import (
    TaskContext,
    TaskManager,
)

# The single TaskManager task type used for all sub-agents. The
# user-facing ``task_type`` is carried inside the task input payload so
# the orchestrator can still distinguish e.g. "research" from "coding".
SUB_AGENT_TASK_TYPE: str = "sub_agent"


class SubAgentRunner:
    """Runs a sub-agent as an async :class:`TaskManager` task.

    A single instance is meant to be reused for the lifetime of the
    process. It registers one task type (``"sub_agent"``) with the
    TaskManager on construction; each call to :meth:`run_sub_agent`
    schedules a new task that runs :meth:`_run`.
    """

    def __init__(
        self,
        task_manager: TaskManager,
        llm: Any = llm_service,
    ) -> None:
        self.task_manager = task_manager
        self._llm = llm
        # Idempotent: only register if not already registered (the
        # TaskManager may be shared across runners / tests).
        if SUB_AGENT_TASK_TYPE not in task_manager.get_registered_types():
            task_manager.register_task_type(SUB_AGENT_TASK_TYPE, self._run)

    # ----------------------------------------------------------- public

    async def run_sub_agent(
        self,
        goal: str,
        task_type: str,
        input: dict[str, Any],
        tools: Optional[list[str]] = None,
    ) -> str:
        """Schedule a sub-agent task and return its task id.

        Args:
            goal: Natural-language objective for the sub-agent.
            task_type: User-facing label (e.g. ``"research"``).
            input: Payload dict handed to the sub-agent.
            tools: Optional subset of main agent tool names the
                sub-agent is allowed to use. Stored for the LLM prompt
                and for the orchestrator's records; no tool dispatch is
                performed here (plugin integration is Task 26).
        """
        payload: dict[str, Any] = {
            "goal": goal,
            "task_type": task_type,
            "input": input,
            "tools": list(tools) if tools else [],
        }
        return await self.task_manager.start_task(
            goal=goal,
            task_type=SUB_AGENT_TASK_TYPE,
            input=payload,
        )

    # ----------------------------------------------------------- task fn

    async def _run(
        self,
        task_id: str,
        input: dict[str, Any],
        ctx: TaskContext,
    ) -> dict[str, Any]:
        """TaskManager task function backing every sub-agent."""
        goal: str = input.get("goal", "")
        sub_type: str = input.get("task_type", "generic")
        user_input: dict[str, Any] = input.get("input", {}) or {}
        tools: list[str] = input.get("tools", []) or []

        await ctx.report_progress("preparing", progress=0.05)

        system_prompt = (
            "You are a focused sub-agent of the Ganesh assistant. "
            "Pursue the assigned goal using only the tools you are "
            "allowed to use. Be concise."
        )
        user_prompt = (
            f"Goal: {goal}\n"
            f"Task type: {sub_type}\n"
            f"Allowed tools: {', '.join(tools) if tools else 'none'}\n"
            f"Input: {json.dumps(user_input, default=str)}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        await ctx.report_progress("calling LLM", progress=0.4)

        response = self._llm.chat_completion(messages=messages, stream=False)

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError) as exc:
            raise RuntimeError(f"Malformed LLM response: {exc}") from exc

        await ctx.report_progress("finalizing", progress=0.9)

        result: dict[str, Any] = {
            "content": content,
            "goal": goal,
            "task_type": sub_type,
            "tools": tools,
            "input": user_input,
        }

        await ctx.report_progress("completed", progress=1.0)
        return result


# ---------------------------------------------------------------------------
# Process-wide singleton (mirrors task_manager / voice_activation pattern)
# ---------------------------------------------------------------------------

_sub_agent_runner: Optional[SubAgentRunner] = None


def get_sub_agent_runner() -> SubAgentRunner:
    """Return the process-wide :class:`SubAgentRunner` singleton."""
    global _sub_agent_runner
    if _sub_agent_runner is None:
        from ganesh_backend.services.task_manager import get_task_manager

        _sub_agent_runner = SubAgentRunner(get_task_manager())
    return _sub_agent_runner


def reset_sub_agent_runner() -> None:
    """Clear the singleton (used by tests)."""
    global _sub_agent_runner
    _sub_agent_runner = None
