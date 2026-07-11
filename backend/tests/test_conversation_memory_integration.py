"""Integration tests for the conversation-checkpoint memory system.

End-to-end tests verifying the full checkpoint memory flow:
chat -> gap -> checkpoint -> continue -> close -> cross-day injection -> on-demand pull.

Uses real ConversationStore (tmp SQLite), real SummaryEmbeddingStore (tmp
LanceDB + HashEmbedder), and real SummaryGenerationService /
ContextAssemblyService. Only the LLM calls (``litellm.completion``) are mocked.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

import main as main_module  # noqa: E402
from ganesh_backend.embeddings import HashEmbedder  # noqa: E402
from ganesh_backend.routers import conversations as conversations_router  # noqa: E402
from ganesh_backend.services import llm as llm_service  # noqa: E402
from ganesh_backend.services.config import config_service  # noqa: E402
from ganesh_backend.services.conversations import ConversationStore  # noqa: E402
from ganesh_backend.services.summary import (  # noqa: E402
    SummaryGenerationService,
    reset_summary_service,
    set_summary_service,
)
from ganesh_backend.services.summary_embeddings import (  # noqa: E402
    SummaryEmbeddingStore,
    reset_summary_embedding_store,
    set_summary_embedding_store,
)
from ganesh_backend.services.summary_retrieval import (  # noqa: E402
    ContextAssemblyService,
    reset_context_assembly_service,
    set_context_assembly_service,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(content: str, model: str = "gpt-4o-mini") -> Any:
    return SimpleNamespace(
        model=model,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ],
    )


class FakeLLM:
    """Configurable fake for ``litellm.completion``.

    Distinguishes call types by inspecting the system message and returns
    the appropriate canned response. Records all calls for later inspection.
    """

    def __init__(
        self,
        chat_response: str = "chat response",
        checkpoint_summary: str = "checkpoint summary text",
        conversation_summary: str = "conversation summary text",
    ) -> None:
        self.chat_response = chat_response
        self.checkpoint_summary = checkpoint_summary
        self.conversation_summary = conversation_summary
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        messages = kwargs.get("messages", [])
        if messages and messages[0].get("role") == "system":
            content = messages[0].get("content", "")
            if "checkpoint summarizer" in content:
                return _make_response(self.checkpoint_summary)
            if "conversation summarizer" in content:
                return _make_response(self.conversation_summary)
        return _make_response(self.chat_response)

    @property
    def chat_calls(self) -> list[dict[str, Any]]:
        """Only the calls that were regular chat (not summary generation)."""
        out: list[dict[str, Any]] = []
        for c in self.calls:
            msgs = c.get("messages", [])
            if msgs and msgs[0].get("role") == "system":
                content = msgs[0].get("content", "")
                if "checkpoint summarizer" in content or "conversation summarizer" in content:
                    continue
            out.append(c)
        return out

    @property
    def checkpoint_calls(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for c in self.calls:
            msgs = c.get("messages", [])
            if msgs and msgs[0].get("role") == "system":
                if "checkpoint summarizer" in msgs[0].get("content", ""):
                    out.append(c)
        return out

    @property
    def conversation_summary_calls(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for c in self.calls:
            msgs = c.get("messages", [])
            if msgs and msgs[0].get("role") == "system":
                if "conversation summarizer" in msgs[0].get("content", ""):
                    out.append(c)
        return out


def _llm_patches(fake: FakeLLM):
    return (
        patch(
            "ganesh_backend.services.llm.litellm.completion",
            side_effect=fake,
        ),
        patch(
            "ganesh_backend.services.llm.get_api_key",
            return_value="test-key",
        ),
    )


def _backdate_all_messages(store: ConversationStore, conv_id: str, minutes: int = 10) -> None:
    """Backdate all messages in a conversation by ``minutes`` ago."""
    old_time = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    with store._conn() as conn:  # type: ignore[attr-defined]
        conn.execute(
            "UPDATE messages SET created_at = ? WHERE conversation_id = ?",
            (old_time, conv_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset all service singletons before and after each test."""
    llm_service.reset_api_key_cache()
    conversations_router.reset_conversation_service()
    reset_summary_service()
    reset_context_assembly_service()
    reset_summary_embedding_store()
    yield
    llm_service.reset_api_key_cache()
    conversations_router.reset_conversation_service()
    reset_summary_service()
    reset_context_assembly_service()
    reset_summary_embedding_store()


@pytest.fixture
def stores(tmp_path: Path) -> SimpleNamespace:
    """Set up real stores + services backed by tmp SQLite + LanceDB."""
    conv_store = ConversationStore(
        sqlite_path=str(tmp_path / "conversations.db"),
        lancedb_uri=str(tmp_path / "lancedb"),
        embedder=HashEmbedder(dimension=64),
        lancedb_collection=f"test_conv_{uuid.uuid4().hex[:8]}",
    )
    emb_store = SummaryEmbeddingStore(
        uri=str(tmp_path / "lancedb_summary"),
        embedder=HashEmbedder(dimension=64),
    )

    conversations_router.set_conversation_service(conv_store)
    set_summary_embedding_store(emb_store)

    summary_svc = SummaryGenerationService(
        conversation_store=conv_store,
        summary_embedding_store=emb_store,
        config=config_service,
    )
    set_summary_service(summary_svc)

    context_svc = ContextAssemblyService(
        conversation_store=conv_store,
        summary_embedding_store=emb_store,
        config=config_service,
    )
    set_context_assembly_service(context_svc)

    return SimpleNamespace(
        conv_store=conv_store,
        emb_store=emb_store,
        summary_svc=summary_svc,
        context_svc=context_svc,
    )


def _client() -> TestClient:
    return TestClient(main_module.create_app())


# ---------------------------------------------------------------------------
# Test 1: Full checkpoint lifecycle
# ---------------------------------------------------------------------------


def test_full_checkpoint_lifecycle(stores: SimpleNamespace) -> None:
    """chat -> gap -> checkpoint -> verify summary, embedding, same conv_id."""
    store = stores.conv_store
    emb_store = stores.emb_store
    fake = FakeLLM(
        chat_response="assistant reply",
        checkpoint_summary="Discussed greeting and Python basics.",
    )
    p1, p2 = _llm_patches(fake)

    with p1, p2:
        client = _client()
        with client:
            # First message — creates conversation.
            resp1 = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "Hello there"}]},
            )
            assert resp1.status_code == 200
            conv_id = resp1.json()["conversation_id"]

            # Second message — same conversation, no gap yet.
            resp2 = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "Tell me about Python"}],
                    "conversation_id": conv_id,
                },
            )
            assert resp2.status_code == 200
            assert resp2.json()["conversation_id"] == conv_id

            # Backdate all messages >5 min to simulate a gap.
            _backdate_all_messages(store, conv_id, minutes=10)

            # Third message — triggers checkpoint, continues SAME conversation.
            resp3 = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "What about decorators?"}],
                    "conversation_id": conv_id,
                },
            )
            assert resp3.status_code == 200
            assert resp3.json()["conversation_id"] == conv_id

    # Verify checkpoint was created.
    checkpoints = store.get_checkpoints(conv_id)
    assert len(checkpoints) == 1
    cp = checkpoints[0]
    assert cp["sequence_number"] == 0
    assert cp["summary"] == "Discussed greeting and Python basics."
    assert cp["start_message_id"] is not None
    assert cp["end_message_id"] is not None

    # The checkpoint should cover the first 4 messages (2 user + 2 assistant),
    # NOT the third user message (persisted after checkpoint generation).
    conv = store.get_conversation(conv_id)
    assert conv is not None
    all_msgs = conv["messages"]
    assert len(all_msgs) >= 5  # at least 4 from first two exchanges + third user msg
    assert cp["start_message_id"] == all_msgs[0]["id"]
    assert cp["end_message_id"] == all_msgs[3]["id"]

    # Verify checkpoint summary is embedded in LanceDB.
    results = emb_store.search_checkpoint_summaries(
        query="Discussed greeting and Python basics.",
        conversation_id=conv_id,
    )
    assert len(results) >= 1
    assert results[0].summary == "Discussed greeting and Python basics."
    assert results[0].conversation_id == conv_id

    # Verify the checkpoint LLM call was made.
    assert len(fake.checkpoint_calls) == 1


# ---------------------------------------------------------------------------
# Test 2: Multiple checkpoints
# ---------------------------------------------------------------------------


def test_multiple_checkpoints(stores: SimpleNamespace) -> None:
    """Two checkpoints: c2 covers only messages since c1, seq increments."""
    store = stores.conv_store
    fake = FakeLLM(
        chat_response="reply",
        checkpoint_summary="segment summary",
    )
    p1, p2 = _llm_patches(fake)

    with p1, p2:
        client = _client()
        with client:
            # First exchange.
            resp1 = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "msg one"}]},
            )
            conv_id = resp1.json()["conversation_id"]

            # Second exchange.
            client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "msg two"}],
                    "conversation_id": conv_id,
                },
            )

            # Gap -> checkpoint c1 (covers messages 1-4).
            _backdate_all_messages(store, conv_id, minutes=10)
            client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "msg three"}],
                    "conversation_id": conv_id,
                },
            )

            # Verify c1.
            cps = store.get_checkpoints(conv_id)
            assert len(cps) == 1
            c1 = cps[0]
            assert c1["sequence_number"] == 0

            # Gap -> checkpoint c2 (covers messages since c1, i.e. msg 5-6).
            _backdate_all_messages(store, conv_id, minutes=10)
            client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "msg four"}],
                    "conversation_id": conv_id,
                },
            )

    cps = store.get_checkpoints(conv_id)
    assert len(cps) == 2
    c2 = cps[1]
    assert c2["sequence_number"] == 1
    assert c2["sequence_number"] == c1["sequence_number"] + 1

    # c2 should cover messages 5-6 (the third exchange, after c1).
    conv = store.get_conversation(conv_id)
    assert conv is not None
    all_msgs = conv["messages"]
    # c1 covered msgs 0-3, c2 should cover msgs 4-5.
    assert c2["start_message_id"] == all_msgs[4]["id"]
    assert c2["end_message_id"] == all_msgs[5]["id"]

    # Verify c2's LLM call only included messages since c1 (msgs 4-5).
    assert len(fake.checkpoint_calls) == 2
    c2_call = fake.checkpoint_calls[1]
    user_msg_content = c2_call["messages"][1]["content"]
    assert "msg three" in user_msg_content or "reply" in user_msg_content
    assert "msg one" not in user_msg_content


# ---------------------------------------------------------------------------
# Test 3: Context includes all checkpoint summaries
# ---------------------------------------------------------------------------


def test_context_includes_all_checkpoint_summaries(stores: SimpleNamespace) -> None:
    """LLM call includes a system message with all checkpoint summaries."""
    store = stores.conv_store
    fake = FakeLLM(chat_response="reply")
    p1, p2 = _llm_patches(fake)

    conv_id = store.create_conversation()
    m1 = store.add_message(conv_id, role="user", content="first")
    store.add_message(conv_id, role="assistant", content="reply1")
    store.create_checkpoint(conv_id, 0, "alpha summary", m1, m1)

    m2 = store.add_message(conv_id, role="user", content="second")
    store.add_message(conv_id, role="assistant", content="reply2")
    store.create_checkpoint(conv_id, 1, "beta summary", m2, m2)

    m3 = store.add_message(conv_id, role="user", content="third")
    store.add_message(conv_id, role="assistant", content="reply3")
    store.create_checkpoint(conv_id, 2, "gamma summary", m3, m3)

    with p1, p2:
        client = _client()
        with client:
            resp = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "new question"}],
                    "conversation_id": conv_id,
                },
            )
            assert resp.status_code == 200

    # The last chat call should include a system message with all 3 summaries.
    chat_calls = fake.chat_calls
    assert len(chat_calls) >= 1
    last_chat_call = chat_calls[-1]
    messages = last_chat_call["messages"]

    system_msgs = [m for m in messages if m["role"] == "system"]
    checkpoint_context = None
    for m in system_msgs:
        if "checkpoint summaries" in m["content"].lower():
            checkpoint_context = m["content"]
            break
    assert checkpoint_context is not None, "No checkpoint context system message found"
    assert "alpha summary" in checkpoint_context
    assert "beta summary" in checkpoint_context
    assert "gamma summary" in checkpoint_context


# ---------------------------------------------------------------------------
# Test 4: On-demand transcript pull
# ---------------------------------------------------------------------------


def test_on_demand_transcript_pull(stores: SimpleNamespace) -> None:
    """User message matching a checkpoint summary triggers transcript pull."""
    store = stores.conv_store
    fake = FakeLLM(chat_response="reply")
    p1, p2 = _llm_patches(fake)

    conv_id = store.create_conversation()
    m0 = store.add_message(conv_id, role="user", content="How do I bake bread?")
    m1 = store.add_message(conv_id, role="assistant", content="Mix flour and water.")
    m2 = store.add_message(conv_id, role="user", content="What temperature?")
    m3 = store.add_message(conv_id, role="assistant", content="350 degrees.")

    # Create a checkpoint with a distinctive summary.
    checkpoint_summary = "Discussed bread baking techniques and temperature."
    cp_id = store.create_checkpoint(conv_id, 0, checkpoint_summary, m0, m3)
    stores.emb_store.index_checkpoint_summary(
        checkpoint_id=cp_id,
        conversation_id=conv_id,
        sequence_number=0,
        summary=checkpoint_summary,
        metadata={"start_message_id": m0, "end_message_id": m3},
    )

    with p1, p2:
        client = _client()
        with client:
            # Send a message that exactly matches the checkpoint summary.
            # HashEmbedder produces score 1.0 for identical text (> 0.85 threshold).
            resp = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": checkpoint_summary}],
                    "conversation_id": conv_id,
                },
            )
            assert resp.status_code == 200

    # Verify the LLM call includes a system message with the pulled transcript.
    chat_calls = fake.chat_calls
    assert len(chat_calls) >= 1
    last_chat_call = chat_calls[-1]
    messages = last_chat_call["messages"]

    system_msgs = [m for m in messages if m["role"] == "system"]
    transcript_msg = None
    for m in system_msgs:
        if "Referenced earlier conversation segment" in m["content"]:
            transcript_msg = m["content"]
            break
    assert transcript_msg is not None, "No pulled transcript system message found"
    # The pulled transcript should include the original messages.
    assert "How do I bake bread?" in transcript_msg
    assert "Mix flour and water." in transcript_msg


# ---------------------------------------------------------------------------
# Test 5: Conversation close generates conversation-level summary
# ---------------------------------------------------------------------------


def test_close_generates_conversation_summary(stores: SimpleNamespace) -> None:
    """POST /close generates summary, embeds it, marks status closed."""
    store = stores.conv_store
    emb_store = stores.emb_store
    fake = FakeLLM(
        chat_response="reply",
        checkpoint_summary="checkpoint summary",
        conversation_summary="The user discussed Python programming in detail.",
    )
    p1, p2 = _llm_patches(fake)

    conv_id = store.create_conversation()
    store.add_message(conv_id, role="user", content="Tell me about Python")
    store.add_message(conv_id, role="assistant", content="Python is great.")
    store.create_checkpoint(conv_id, 0, "Python discussion", None, None)

    with p1, p2:
        client = _client()
        with client:
            resp = client.post(f"/api/conversations/{conv_id}/close")
            assert resp.status_code == 200
            body = resp.json()
            assert body["conversation_id"] == conv_id
            assert body["summary"] == "The user discussed Python programming in detail."
            assert body["status"] == "closed"

    # Verify conversation summary stored.
    conv = store.get_conversation(conv_id)
    assert conv is not None
    assert conv["summary"] == "The user discussed Python programming in detail."
    assert conv["status"] == "closed"
    assert conv["closed_at"] is not None

    # Verify conversation summary embedded in LanceDB.
    results = emb_store.search_conversation_summaries(
        query="The user discussed Python programming in detail.",
        exclude_conversation_id=None,
    )
    assert len(results) >= 1
    matched = [r for r in results if r.conversation_id == conv_id]
    assert len(matched) >= 1
    assert matched[0].summary == "The user discussed Python programming in detail."

    # Verify conversation summary LLM call was made.
    assert len(fake.conversation_summary_calls) == 1


# ---------------------------------------------------------------------------
# Test 6: Cross-day memory injection
# ---------------------------------------------------------------------------


def test_cross_day_memory_injection(stores: SimpleNamespace) -> None:
    """Closed conversation summary is injected into a new conversation."""
    store = stores.conv_store
    fake = FakeLLM(
        chat_response="reply",
        checkpoint_summary="checkpoint summary",
        conversation_summary="User explored Rust ownership and borrowing concepts.",
    )
    p1, p2 = _llm_patches(fake)

    # Day 1: create and close a conversation.
    conv1 = store.create_conversation()
    store.add_message(conv1, role="user", content="Explain Rust ownership")
    store.add_message(conv1, role="assistant", content="Ownership is...")
    store.create_checkpoint(conv1, 0, "Rust ownership", None, None)

    with p1, p2:
        client = _client()
        with client:
            resp = client.post(f"/api/conversations/{conv1}/close")
            assert resp.status_code == 200
            assert resp.json()["summary"] == "User explored Rust ownership and borrowing concepts."

            # Day 2: start a new conversation with a message matching the
            # closed conversation's summary (exact text -> score 1.0).
            resp2 = client.post(
                "/api/chat",
                json={
                    "messages": [
                        {
                            "role": "user",
                            "content": "User explored Rust ownership and borrowing concepts.",
                        }
                    ],
                },
            )
            assert resp2.status_code == 200
            new_conv_id = resp2.json()["conversation_id"]
            assert new_conv_id != conv1

    # Verify the LLM call for the new conversation includes cross-day context.
    chat_calls = fake.chat_calls
    # The last chat call should be for the new conversation.
    last_chat_call = chat_calls[-1]
    messages = last_chat_call["messages"]

    system_msgs = [m for m in messages if m["role"] == "system"]
    cross_day_msg = None
    for m in system_msgs:
        if "Past conversation context" in m["content"]:
            cross_day_msg = m["content"]
            break
    assert cross_day_msg is not None, "No cross-day context system message found"
    assert "User explored Rust ownership and borrowing concepts." in cross_day_msg


# ---------------------------------------------------------------------------
# Test 7: Close endpoint generates final checkpoint
# ---------------------------------------------------------------------------


def test_close_generates_final_checkpoint(stores: SimpleNamespace) -> None:
    """Close endpoint creates a final checkpoint for unsummarized messages."""
    store = stores.conv_store
    fake = FakeLLM(
        chat_response="reply",
        checkpoint_summary="final segment summary",
        conversation_summary="comprehensive conversation summary",
    )
    p1, p2 = _llm_patches(fake)

    conv_id = store.create_conversation()
    # First segment: messages + checkpoint.
    m0 = store.add_message(conv_id, role="user", content="first question")
    m1 = store.add_message(conv_id, role="assistant", content="first answer")
    store.create_checkpoint(conv_id, 0, "first checkpoint summary", m0, m1)

    # Unsummarized segment (at least min_messages_for_checkpoint=2).
    store.add_message(conv_id, role="user", content="second question")
    store.add_message(conv_id, role="assistant", content="second answer")

    assert store.get_checkpoint_count(conv_id) == 1

    with p1, p2:
        client = _client()
        with client:
            resp = client.post(f"/api/conversations/{conv_id}/close")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "closed"
            assert body["summary"] == "comprehensive conversation summary"

    # A final checkpoint should have been created for the unsummarized segment.
    assert store.get_checkpoint_count(conv_id) == 2
    cps = store.get_checkpoints(conv_id)
    final_cp = cps[1]
    assert final_cp["sequence_number"] == 1
    assert final_cp["summary"] == "final segment summary"

    # Verify the conversation summary LLM call includes both checkpoint summaries.
    conv_summary_calls = fake.conversation_summary_calls
    assert len(conv_summary_calls) == 1
    call_messages = conv_summary_calls[0]["messages"]
    system_content = call_messages[0]["content"]
    assert "first checkpoint summary" in system_content
    assert "final segment summary" in system_content

    # Verify conversation is closed with summary.
    conv = store.get_conversation(conv_id)
    assert conv is not None
    assert conv["status"] == "closed"
    assert conv["summary"] == "comprehensive conversation summary"
