"""Tests for the sub-agent orchestration system.

Covers:
    - test_spawn_sub_agent          — spawning returns a task id and the
                                      sub-agent runs to completion.
    - test_query_status_non_blocking — query_sub_agent_status returns a
                                      summary without blocking on the
                                      running task.
    - test_result_piped_to_main     — get_sub_agent_result returns the
                                      completed result and the
                                      orchestrator can build a context
                                      message injecting it into the main
                                      agent's LLM context.

The LLM service is mocked so no real API key / network call is needed.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from ganesh_backend.services.orchestrator import Orchestrator  # noqa: E402
from ganesh_backend.services.sub_agent import SubAgentRunner  # noqa: E402
from ganesh_backend.services.task_manager import (  # noqa: E402
    TaskManager,
    TaskStatus,
)


def _fake_llm_response(content: str = "sub-agent output") -> Any:
    """Build a LiteLLM-shaped response object with a single choice."""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.fixture
def task_manager(tmp_path: Path) -> TaskManager:
    db_path = str(tmp_path / "ganesh.db")
    return TaskManager(db_path=db_path)


@pytest.fixture
def mock_llm() -> Any:
    llm = MagicMock()
    llm.chat_completion = MagicMock(return_value=_fake_llm_response("hello"))
    return llm


@pytest.fixture
def orchestrator(
    task_manager: TaskManager, mock_llm: Any
) -> Orchestrator:
    runner = SubAgentRunner(task_manager, llm=mock_llm)
    return Orchestrator(task_manager=task_manager, runner=runner)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spawn_sub_agent(orchestrator: Orchestrator) -> None:
    task_id = await orchestrator.spawn_sub_agent(
        goal="summarise the notes",
        task_type="research",
        input={"notes": "abc"},
        tools=["search"],
    )
    assert isinstance(task_id, str)
    assert len(task_id) > 0
    # Wait for the async task to settle.
    await asyncio.sleep(0.2)
    info = orchestrator.task_manager.get_task(task_id)
    assert info is not None
    assert info["status"] == TaskStatus.COMPLETED.value
    assert info["goal"] == "summarise the notes"


@pytest.mark.asyncio
async def test_query_status_non_blocking(orchestrator: Orchestrator) -> None:
    task_id = await orchestrator.spawn_sub_agent(
        goal="long running",
        task_type="coding",
        input={},
    )
    # Query immediately — the task is still pending/running. This must
    # not block on the asyncio task completing.
    summary = orchestrator.query_sub_agent_status(task_id)
    assert summary is not None
    assert summary["task_id"] == task_id
    assert summary["goal"] == "long running"
    assert summary["status"] in (
        TaskStatus.PENDING.value,
        TaskStatus.RUNNING.value,
    )
    # Let it finish so the background task isn't pending at teardown.
    await asyncio.sleep(0.2)
    final = orchestrator.query_sub_agent_status(task_id)
    assert final is not None
    assert final["status"] == TaskStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_result_piped_to_main(orchestrator: Orchestrator) -> None:
    task_id = await orchestrator.spawn_sub_agent(
        goal="produce a finding",
        task_type="research",
        input={"topic": "x"},
    )
    await asyncio.sleep(0.2)
    # Result is fetched only once the task is terminal.
    result_info = orchestrator.get_sub_agent_result(task_id)
    assert result_info is not None
    assert result_info["status"] == TaskStatus.COMPLETED.value
    result = result_info["result"]
    assert isinstance(result, dict)
    assert result["content"] == "hello"
    assert result["goal"] == "produce a finding"

    # The orchestrator can build a system message injecting the result
    # into the main agent's LLM context.
    msg = orchestrator.build_result_context_message(task_id)
    assert msg is not None
    assert msg["role"] == "system"
    assert "hello" in msg["content"]
    assert task_id in msg["content"]
