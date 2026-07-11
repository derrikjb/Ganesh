"""Tests for the ContextAssemblyService (context window builder).

The service assembles the full context window for each chat turn:
checkpoint summaries (always), cross-day conversation summaries (if relevant),
and on-demand full transcript pulls (when semantically triggered).

All tests mock ConversationStore and SummaryEmbeddingStore so no real
LanceDB or SQLite is needed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from ganesh_backend.services.summary_embeddings import (  # noqa: E402
    CheckpointSearchResult,
    ConversationSearchResult,
)
from ganesh_backend.services.summary_retrieval import (  # noqa: E402
    ContextAssemblyService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_checkpoint(
    seq: int,
    summary: str,
    start_id: str | None = None,
    end_id: str | None = None,
    created_at: str = "2025-01-01T10:00:00+00:00",
    cp_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": cp_id or f"cp-{seq}",
        "conversation_id": "conv-1",
        "sequence_number": seq,
        "summary": summary,
        "start_message_id": start_id or f"msg-start-{seq}",
        "end_message_id": end_id or f"msg-end-{seq}",
        "created_at": created_at,
    }


def _make_message(msg_id: str, role: str, content: str) -> dict[str, str]:
    return {
        "id": msg_id,
        "role": role,
        "content": content,
        "created_at": "2025-01-01T10:00:00+00:00",
    }


def _make_config(
    max_summaries_injected: int = 3,
    full_pull_threshold: float = 0.85,
    max_transcript_messages: int = 50,
    adjacent_segments: int = 1,
) -> MagicMock:
    """Mock config service returning the given conversation_memory settings."""
    cfg = MagicMock()
    settings = {
        "conversation_memory.max_summaries_injected": max_summaries_injected,
        "conversation_memory.full_pull_threshold": full_pull_threshold,
        "conversation_memory.max_transcript_messages": max_transcript_messages,
        "conversation_memory.adjacent_segments": adjacent_segments,
    }

    def get_setting(key: str, default: Any = None) -> Any:
        return settings.get(key, default)

    cfg.get_setting.side_effect = get_setting
    return cfg


def _make_stores(
    checkpoints: list[dict[str, Any]] | None = None,
    checkpoint_search_results: list[CheckpointSearchResult] | None = None,
    conversation_search_results: list[ConversationSearchResult] | None = None,
    messages_between: list[dict[str, Any]] | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Build mocked ConversationStore and SummaryEmbeddingStore."""
    conv_store = MagicMock()
    conv_store.get_checkpoints.return_value = checkpoints or []
    conv_store.get_checkpoint.side_effect = lambda cid, seq: next(
        (c for c in (checkpoints or []) if c["sequence_number"] == seq),
        None,
    )
    conv_store.get_messages_between.return_value = messages_between or []

    emb_store = MagicMock()
    emb_store.search_checkpoint_summaries.return_value = (
        checkpoint_search_results or []
    )
    emb_store.search_conversation_summaries.return_value = (
        conversation_search_results or []
    )
    return conv_store, emb_store


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_context_no_checkpoints_returns_existing_plus_user_msg() -> None:
    """With no checkpoints, context is just existing_messages (user msg already included)."""
    conv_store, emb_store = _make_stores(checkpoints=[])
    svc = ContextAssemblyService(conv_store, emb_store, _make_config())

    existing = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    result = svc.build_context("what's up?", "conv-1", existing)

    assert result == existing


def test_build_context_with_checkpoints_prepends_checkpoint_context() -> None:
    """Checkpoints produce a system message prepended before existing_messages."""
    cps = [
        _make_checkpoint(0, "Talked about Python.", created_at="2025-01-01T09:15:00+00:00"),
        _make_checkpoint(1, "Discussed testing.", created_at="2025-01-01T10:30:00+00:00"),
    ]
    conv_store, emb_store = _make_stores(checkpoints=cps)
    svc = ContextAssemblyService(conv_store, emb_store, _make_config())

    existing = [{"role": "user", "content": "hi"}]
    result = svc.build_context("more", "conv-1", existing)

    assert result[0]["role"] == "system"
    assert "Conversation memory" in result[0]["content"]
    assert {"role": "user", "content": "hi"} in result


def test_checkpoint_context_includes_all_summaries_in_order() -> None:
    """The checkpoint context message lists all summaries in sequence order."""
    cps = [
        _make_checkpoint(0, "First checkpoint summary.", created_at="2025-01-01T09:15:00+00:00"),
        _make_checkpoint(1, "Second checkpoint summary.", created_at="2025-01-01T10:30:00+00:00"),
        _make_checkpoint(2, "Third checkpoint summary.", created_at="2025-01-01T14:45:00+00:00"),
    ]
    conv_store, emb_store = _make_stores(checkpoints=cps)
    svc = ContextAssemblyService(conv_store, emb_store, _make_config())

    msg = svc._build_checkpoint_context_message("conv-1")
    assert msg is not None
    content = msg["content"]
    assert "First checkpoint summary." in content
    assert "Second checkpoint summary." in content
    assert "Third checkpoint summary." in content
    assert content.index("First checkpoint summary.") < content.index("Second checkpoint summary.")
    assert content.index("Second checkpoint summary.") < content.index("Third checkpoint summary.")


def test_build_context_with_relevant_past_conversations_prepends_cross_day() -> None:
    """Relevant past conversation summaries produce a cross-day system message."""
    conv_store, emb_store = _make_stores(
        checkpoints=[],
        conversation_search_results=[
            ConversationSearchResult(
                conversation_id="conv-old-1",
                summary="Discussed React hooks in depth.",
                score=0.92,
                metadata={"title": "React chat", "created_at": "2024-12-31T15:00:00+00:00"},
            ),
        ],
    )
    svc = ContextAssemblyService(conv_store, emb_store, _make_config())
    result = svc.build_context("tell me about hooks", "conv-1", [])

    cross_day_msgs = [
        m for m in result if m["role"] == "system" and "Past conversation context" in m["content"]
    ]
    assert len(cross_day_msgs) == 1
    assert "React hooks" in cross_day_msgs[0]["content"]


def test_build_context_excludes_current_conversation_from_cross_day_search() -> None:
    """The current conversation_id is passed as exclude_conversation_id."""
    conv_store, emb_store = _make_stores(
        checkpoints=[],
        conversation_search_results=[],
    )
    svc = ContextAssemblyService(conv_store, emb_store, _make_config())
    svc.build_context("query", "conv-current", [])

    emb_store.search_conversation_summaries.assert_called_once()
    call_kwargs = emb_store.search_conversation_summaries.call_args.kwargs
    assert call_kwargs.get("exclude_conversation_id") == "conv-current"


def test_cross_day_returns_none_when_all_scores_below_minimum() -> None:
    """Scores below 0.3 minimum threshold produce no cross-day message."""
    conv_store, emb_store = _make_stores(
        checkpoints=[],
        conversation_search_results=[
            ConversationSearchResult(
                conversation_id="conv-old",
                summary="irrelevant",
                score=0.2,
                metadata={"title": "old", "created_at": "2024-12-31T15:00:00+00:00"},
            ),
        ],
    )
    svc = ContextAssemblyService(conv_store, emb_store, _make_config())
    msg = svc._build_cross_day_context_message("query", "conv-1")
    assert msg is None


def test_build_context_high_similarity_prepends_pulled_transcript() -> None:
    """A checkpoint match above threshold triggers a transcript pull."""
    cps = [
        _make_checkpoint(0, "Talked about databases.", start_id="m0", end_id="m1"),
        _make_checkpoint(1, "Discussed SQL vs NoSQL.", start_id="m2", end_id="m3"),
        _make_checkpoint(2, "Covered indexing.", start_id="m4", end_id="m5"),
    ]
    search_results = [
        CheckpointSearchResult(
            checkpoint_id="cp-1",
            conversation_id="conv-1",
            sequence_number=1,
            summary="Discussed SQL vs NoSQL.",
            score=0.9,
            metadata={
                "start_message_id": "m2",
                "end_message_id": "m3",
                "created_at": "2025-01-01T10:30:00+00:00",
            },
        ),
    ]
    messages = [
        _make_message("m0", "user", "what is a db"),
        _make_message("m1", "assistant", "a database stores data"),
        _make_message("m2", "user", "sql vs nosql?"),
        _make_message("m3", "assistant", "sql is structured, nosql is not"),
        _make_message("m4", "user", "indexing?"),
        _make_message("m5", "assistant", "indexes speed up queries"),
    ]
    conv_store, emb_store = _make_stores(
        checkpoints=cps,
        checkpoint_search_results=search_results,
        messages_between=messages,
    )
    svc = ContextAssemblyService(conv_store, emb_store, _make_config())
    result = svc.build_context("tell me about sql vs nosql", "conv-1", [])

    transcript_msgs = [
        m for m in result if m["role"] == "system" and "Referenced earlier conversation segment" in m["content"]
    ]
    assert len(transcript_msgs) == 1
    assert "sql vs nosql" in transcript_msgs[0]["content"].lower() or "sql" in transcript_msgs[0]["content"].lower()


def test_pulled_transcript_includes_adjacent_segments() -> None:
    """Adjacent checkpoints (cK-1 and cK+1) are included in the pull."""
    cps = [
        _make_checkpoint(0, "Talked about databases.", start_id="m0", end_id="m1"),
        _make_checkpoint(1, "Discussed SQL vs NoSQL.", start_id="m2", end_id="m3"),
        _make_checkpoint(2, "Covered indexing.", start_id="m4", end_id="m5"),
    ]
    search_results = [
        CheckpointSearchResult(
            checkpoint_id="cp-1",
            conversation_id="conv-1",
            sequence_number=1,
            summary="Discussed SQL vs NoSQL.",
            score=0.9,
            metadata={
                "start_message_id": "m2",
                "end_message_id": "m3",
                "created_at": "2025-01-01T10:30:00+00:00",
            },
        ),
    ]
    messages = [
        _make_message("m0", "user", "what is a db"),
        _make_message("m1", "assistant", "a database stores data"),
        _make_message("m2", "user", "sql vs nosql?"),
        _make_message("m3", "assistant", "sql is structured, nosql is not"),
        _make_message("m4", "user", "indexing?"),
        _make_message("m5", "assistant", "indexes speed up queries"),
    ]
    conv_store, emb_store = _make_stores(
        checkpoints=cps,
        checkpoint_search_results=search_results,
        messages_between=messages,
    )
    svc = ContextAssemblyService(conv_store, emb_store, _make_config())
    msg = svc._build_pulled_transcript_message("sql vs nosql", "conv-1")
    assert msg is not None
    content = msg["content"]
    assert "what is a db" in content
    assert "indexing?" in content


def test_pulled_transcript_truncated_to_max_transcript_messages() -> None:
    """When the pulled segment exceeds max_transcript_messages, it's truncated."""
    cps = [
        _make_checkpoint(0, "cp0", start_id="m0", end_id="m9"),
        _make_checkpoint(1, "cp1", start_id="m10", end_id="m19"),
        _make_checkpoint(2, "cp2", start_id="m20", end_id="m29"),
    ]
    search_results = [
        CheckpointSearchResult(
            checkpoint_id="cp-1",
            conversation_id="conv-1",
            sequence_number=1,
            summary="cp1",
            score=0.9,
            metadata={
                "start_message_id": "m10",
                "end_message_id": "m19",
                "created_at": "2025-01-01T10:30:00+00:00",
            },
        ),
    ]
    messages = [
        _make_message(f"m{i}", "user" if i % 2 == 0 else "assistant", f"msg-{i}")
        for i in range(30)
    ]
    conv_store, emb_store = _make_stores(
        checkpoints=cps,
        checkpoint_search_results=search_results,
        messages_between=messages,
    )
    svc = ContextAssemblyService(conv_store, emb_store, _make_config(max_transcript_messages=5))
    msg = svc._build_pulled_transcript_message("query", "conv-1")
    assert msg is not None
    content = msg["content"]
    line_count = sum(
        1 for line in content.splitlines()
        if line.startswith("User:") or line.startswith("Assistant:")
    )
    assert line_count <= 5
    assert "msg-29" in content
    assert "msg-0" not in content


def test_build_context_low_similarity_does_not_prepend_transcript() -> None:
    """A checkpoint match below threshold does NOT trigger a transcript pull."""
    cps = [_make_checkpoint(0, "Talked about databases.", start_id="m0", end_id="m1")]
    search_results = [
        CheckpointSearchResult(
            checkpoint_id="cp-0",
            conversation_id="conv-1",
            sequence_number=0,
            summary="Talked about databases.",
            score=0.5,
            metadata={
                "start_message_id": "m0",
                "end_message_id": "m1",
                "created_at": "2025-01-01T10:00:00+00:00",
            },
        ),
    ]
    conv_store, emb_store = _make_stores(
        checkpoints=cps,
        checkpoint_search_results=search_results,
        messages_between=[],
    )
    svc = ContextAssemblyService(conv_store, emb_store, _make_config())
    result = svc.build_context("unrelated query", "conv-1", [])

    transcript_msgs = [
        m for m in result if m["role"] == "system" and "Referenced earlier conversation segment" in m["content"]
    ]
    assert len(transcript_msgs) == 0


def test_all_three_system_messages_prepended_in_correct_order() -> None:
    """When all conditions are met, messages are in order: checkpoint, cross-day, transcript."""
    cps = [
        _make_checkpoint(0, "Talked about databases.", start_id="m0", end_id="m1"),
        _make_checkpoint(1, "Discussed SQL vs NoSQL.", start_id="m2", end_id="m3"),
        _make_checkpoint(2, "Covered indexing.", start_id="m4", end_id="m5"),
    ]
    checkpoint_results = [
        CheckpointSearchResult(
            checkpoint_id="cp-1",
            conversation_id="conv-1",
            sequence_number=1,
            summary="Discussed SQL vs NoSQL.",
            score=0.9,
            metadata={
                "start_message_id": "m2",
                "end_message_id": "m3",
                "created_at": "2025-01-01T10:30:00+00:00",
            },
        ),
    ]
    conversation_results = [
        ConversationSearchResult(
            conversation_id="conv-old",
            summary="Old database discussion.",
            score=0.88,
            metadata={"title": "DB chat", "created_at": "2024-12-31T15:00:00+00:00"},
        ),
    ]
    messages = [
        _make_message("m0", "user", "what is a db"),
        _make_message("m1", "assistant", "a database stores data"),
        _make_message("m2", "user", "sql vs nosql?"),
        _make_message("m3", "assistant", "sql is structured, nosql is not"),
        _make_message("m4", "user", "indexing?"),
        _make_message("m5", "assistant", "indexes speed up queries"),
    ]
    conv_store, emb_store = _make_stores(
        checkpoints=cps,
        checkpoint_search_results=checkpoint_results,
        conversation_search_results=conversation_results,
        messages_between=messages,
    )
    svc = ContextAssemblyService(conv_store, emb_store, _make_config())
    existing = [{"role": "user", "content": "existing"}]
    result = svc.build_context("sql vs nosql", "conv-1", existing)

    system_msgs = [m for m in result if m["role"] == "system"]
    assert len(system_msgs) == 3
    assert "Conversation memory" in system_msgs[0]["content"]
    assert "Past conversation context" in system_msgs[1]["content"]
    assert "Referenced earlier conversation segment" in system_msgs[2]["content"]

    assert result[len(system_msgs)] == {"role": "user", "content": "existing"}


def test_build_context_preserves_existing_and_appends_user_message() -> None:
    """existing_messages are preserved verbatim; no user message is appended."""
    conv_store, emb_store = _make_stores(checkpoints=[])
    svc = ContextAssemblyService(conv_store, emb_store, _make_config())
    existing = [
        {"role": "system", "content": "you are ganesh"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]
    result = svc.build_context("next question", "conv-1", existing)

    assert result == existing


def test_checkpoint_context_empty_summaries_skipped() -> None:
    """If all checkpoint summaries are empty/None, no checkpoint context message."""
    cps = [
        _make_checkpoint(0, "", created_at="2025-01-01T09:15:00+00:00"),
        _make_checkpoint(1, "   ", created_at="2025-01-01T10:30:00+00:00"),
    ]
    conv_store, emb_store = _make_stores(checkpoints=cps)
    svc = ContextAssemblyService(conv_store, emb_store, _make_config())
    msg = svc._build_checkpoint_context_message("conv-1")
    assert msg is None


def test_singleton_get_reset_set() -> None:
    """The singleton accessors work as expected."""
    from ganesh_backend.services import summary_retrieval as mod

    mod.reset_context_assembly_service()
    assert mod._service is None

    fake = MagicMock(spec=ContextAssemblyService)
    mod.set_context_assembly_service(fake)
    assert mod.get_context_assembly_service() is fake

    mod.reset_context_assembly_service()
    assert mod._service is None
