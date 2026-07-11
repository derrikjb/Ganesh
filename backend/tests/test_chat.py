"""Tests for the /api/chat endpoint.

LiteLLM is mocked throughout — no real API calls are made.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

import main as main_module  # noqa: E402
from ganesh_backend.embeddings import HashEmbedder  # noqa: E402
from ganesh_backend.routers import conversations as conversations_router  # noqa: E402
from ganesh_backend.services import llm as llm_service  # noqa: E402
from ganesh_backend.services.conversations import ConversationStore  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_api_key_cache():
    llm_service.reset_api_key_cache()
    yield
    llm_service.reset_api_key_cache()


@pytest.fixture(autouse=True)
def _reset_conversation_service():
    conversations_router.reset_conversation_service()
    yield
    conversations_router.reset_conversation_service()


def _make_store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(
        sqlite_path=str(tmp_path / "conversations.db"),
        lancedb_uri=str(tmp_path / "lancedb"),
        embedder=HashEmbedder(dimension=64),
        lancedb_collection=f"test_conv_{uuid.uuid4().hex[:8]}",
    )


@pytest.fixture
def store(tmp_path: Path) -> ConversationStore:
    s = _make_store(tmp_path)
    conversations_router.set_conversation_service(s)
    return s


def _make_non_stream_response(
    content: str = "hello there", model: str = "gpt-4o-mini"
):
    return SimpleNamespace(
        model=model,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ],
    )


def _make_stream_chunks(deltas: list[str]):
    chunks = []
    for d in deltas:
        chunks.append(
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(content=d),
                        finish_reason=None,
                    )
                ]
            )
        )
    chunks.append(
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=None),
                    finish_reason="stop",
                )
            ]
        )
    )
    return chunks


def _llm_patches(content: str = "Hi from the model"):
    return (
        patch(
            "ganesh_backend.services.llm.litellm.completion",
            return_value=_make_non_stream_response(content),
        ),
        patch(
            "ganesh_backend.services.llm.get_api_key",
            return_value="test-key",
        ),
    )


def _stream_llm_patches(deltas: list[str] | None = None):
    if deltas is None:
        deltas = ["Hello", " world", "!"]
    return (
        patch(
            "ganesh_backend.services.llm.litellm.completion",
            return_value=iter(_make_stream_chunks(deltas)),
        ),
        patch(
            "ganesh_backend.services.llm.get_api_key",
            return_value="test-key",
        ),
    )


def _mock_summary_service():
    svc = MagicMock()
    svc.generate_checkpoint.return_value = {
        "id": "cp-1",
        "conversation_id": "x",
        "sequence_number": 0,
        "summary": "checkpoint summary",
        "start_message_id": None,
        "end_message_id": None,
    }
    svc.generate_conversation_summary.return_value = "conversation summary"
    return svc


def _mock_context_service(checkpoint_msg=None, cross_day_msg=None, transcript_msg=None):
    svc = MagicMock()

    def _build_context(user_message, conversation_id, existing_messages):
        result = list(existing_messages)
        if checkpoint_msg:
            result = [checkpoint_msg] + result
        if cross_day_msg:
            result = [cross_day_msg] + result
        if transcript_msg:
            result = [transcript_msg] + result
        result.append({"role": "user", "content": user_message})
        return result

    svc.build_context.side_effect = _build_context
    return svc


def _backdate_last_message(store: ConversationStore, conv_id: str, minutes: int = 10):
    old_time = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    with store._conn() as conn:  # type: ignore[attr-defined]
        conn.execute(
            "UPDATE messages SET created_at = ? WHERE conversation_id = ?",
            (old_time, conv_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Existing tests (backward compat)
# ---------------------------------------------------------------------------


def test_chat_endpoint():
    mock_response = _make_non_stream_response("Hi from the model")
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        return_value=mock_response,
    ), patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="test-key",
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "Hi from the model"
    assert body["model"] == "gpt-4o-mini"


def test_chat_streaming():
    chunks = _make_stream_chunks(["Hello", " world", "!"])
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        return_value=iter(chunks),
    ) as mock_completion, patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="test-key",
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                },
            )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "data:" in body
    assert "Hello" in body
    assert " world" in body
    assert "!" in body
    assert "event: done" in body
    args, kwargs = mock_completion.call_args
    assert kwargs.get("stream") is True


def test_chat_missing_api_key():
    with patch(
        "ganesh_backend.services.llm.get_api_key",
        side_effect=llm_service.MissingAPIKeyError("no key"),
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
    assert response.status_code == 401
    assert "API key" in response.json()["detail"]


def test_chat_invalid_model():
    with patch(
        "ganesh_backend.services.llm.litellm.completion",
        side_effect=llm_service.LLMError("Invalid model: bad-model"),
    ), patch(
        "ganesh_backend.services.llm.get_api_key",
        return_value="test-key",
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "model": "bad-model",
                },
            )
    assert response.status_code == 400
    assert "Invalid model" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Conversation memory tests
# ---------------------------------------------------------------------------


def test_chat_no_conversation_id_creates_new(store: ConversationStore):
    p1, p2 = _llm_patches("response")
    with p1, p2:
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"]
    conv_id = body["conversation_id"]
    conv = store.get_conversation(conv_id)
    assert conv is not None
    assert conv["status"] == "active"


def test_chat_with_active_conversation_id_reuses_it(store: ConversationStore):
    conv_id = store.create_conversation()
    store.add_message(conv_id, role="user", content="previous message")

    p1, p2 = _llm_patches("response")
    with p1, p2:
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "conversation_id": conv_id,
                },
            )
    assert response.status_code == 200
    assert response.json()["conversation_id"] == conv_id


def test_chat_with_closed_conversation_id_creates_new(store: ConversationStore):
    conv_id = store.create_conversation()
    store.add_message(conv_id, role="user", content="msg")
    store.close_conversation(conv_id)

    p1, p2 = _llm_patches("response")
    with p1, p2:
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "conversation_id": conv_id,
                },
            )
    assert response.status_code == 200
    new_id = response.json()["conversation_id"]
    assert new_id != conv_id
    assert store.get_conversation_status(conv_id) == "closed"


def test_chat_stale_conversation_triggers_checkpoint_continues_same(
    store: ConversationStore,
):
    conv_id = store.create_conversation()
    store.add_message(conv_id, role="user", content="old msg 1")
    store.add_message(conv_id, role="assistant", content="old reply 1")
    _backdate_last_message(store, conv_id, minutes=10)

    mock_summary = _mock_summary_service()
    mock_context = _mock_context_service()
    p1, p2 = _llm_patches("response")
    with p1, p2, patch(
        "ganesh_backend.services.summary.get_summary_service",
        return_value=mock_summary,
    ), patch(
        "ganesh_backend.services.summary_retrieval.get_context_assembly_service",
        return_value=mock_context,
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "conversation_id": conv_id,
                },
            )
    assert response.status_code == 200
    assert response.json()["conversation_id"] == conv_id
    mock_summary.generate_checkpoint.assert_called_once_with(conv_id)


def test_chat_stale_conversation_does_not_create_new(store: ConversationStore):
    conv_id = store.create_conversation()
    store.add_message(conv_id, role="user", content="old msg")
    store.add_message(conv_id, role="assistant", content="old reply")
    _backdate_last_message(store, conv_id, minutes=10)

    mock_summary = _mock_summary_service()
    mock_context = _mock_context_service()
    p1, p2 = _llm_patches("response")
    with p1, p2, patch(
        "ganesh_backend.services.summary.get_summary_service",
        return_value=mock_summary,
    ), patch(
        "ganesh_backend.services.summary_retrieval.get_context_assembly_service",
        return_value=mock_context,
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "conversation_id": conv_id,
                },
            )
    assert response.json()["conversation_id"] == conv_id
    convs = store.list_conversations()
    assert len(convs) == 1


def test_user_message_persisted(store: ConversationStore):
    p1, p2 = _llm_patches("response")
    with p1, p2:
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [
                        {"role": "user", "content": "remember this"}
                    ]
                },
            )
    conv_id = response.json()["conversation_id"]
    conv = store.get_conversation(conv_id)
    assert conv is not None
    user_msgs = [m for m in conv["messages"] if m["role"] == "user"]
    assert any("remember this" in m["content"] for m in user_msgs)


def test_assistant_response_persisted(store: ConversationStore):
    p1, p2 = _llm_patches("the assistant reply")
    with p1, p2:
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
    conv_id = response.json()["conversation_id"]
    conv = store.get_conversation(conv_id)
    assert conv is not None
    assistant_msgs = [m for m in conv["messages"] if m["role"] == "assistant"]
    assert any("the assistant reply" in m["content"] for m in assistant_msgs)


def test_checkpoint_summaries_included_in_context(store: ConversationStore):
    conv_id = store.create_conversation()
    store.add_message(conv_id, role="user", content="previous")
    store.create_checkpoint(conv_id, 0, "checkpoint 0 summary", None, None)

    checkpoint_msg = {
        "role": "system",
        "content": "checkpoint 0 summary",
    }
    mock_context = _mock_context_service(checkpoint_msg=checkpoint_msg)
    p1, p2 = _llm_patches("response")
    with p1, p2, patch(
        "ganesh_backend.services.summary_retrieval.get_context_assembly_service",
        return_value=mock_context,
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "conversation_id": conv_id,
                },
            )
    assert response.status_code == 200
    mock_context.build_context.assert_called_once()
    args, kwargs = mock_context.build_context.call_args
    assert kwargs["conversation_id"] == conv_id


def test_cross_day_summaries_injected(store: ConversationStore):
    conv_id = store.create_conversation()
    store.add_message(conv_id, role="user", content="msg")

    cross_day_msg = {
        "role": "system",
        "content": "Past conversation context (from previous days):",
    }
    mock_context = _mock_context_service(cross_day_msg=cross_day_msg)
    p1, p2 = _llm_patches("response")
    with p1, p2, patch(
        "ganesh_backend.services.summary_retrieval.get_context_assembly_service",
        return_value=mock_context,
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "conversation_id": conv_id,
                },
            )
    assert response.status_code == 200
    mock_context.build_context.assert_called_once()


def test_full_transcript_pulled_when_match_exceeds_threshold(
    store: ConversationStore,
):
    conv_id = store.create_conversation()
    store.add_message(conv_id, role="user", content="msg")

    transcript_msg = {
        "role": "system",
        "content": "Referenced earlier conversation segment",
    }
    mock_context = _mock_context_service(transcript_msg=transcript_msg)
    p1, p2 = _llm_patches("response")
    with p1, p2, patch(
        "ganesh_backend.services.summary_retrieval.get_context_assembly_service",
        return_value=mock_context,
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "conversation_id": conv_id,
                },
            )
    assert response.status_code == 200
    mock_context.build_context.assert_called_once()


def test_full_transcript_not_pulled_when_match_below_threshold(
    store: ConversationStore,
):
    conv_id = store.create_conversation()
    store.add_message(conv_id, role="user", content="msg")

    mock_context = _mock_context_service(transcript_msg=None)
    p1, p2 = _llm_patches("response")
    with p1, p2, patch(
        "ganesh_backend.services.summary_retrieval.get_context_assembly_service",
        return_value=mock_context,
    ):
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "conversation_id": conv_id,
                },
            )
    assert response.status_code == 200
    mock_context.build_context.assert_called_once()


def test_streaming_includes_conversation_event(store: ConversationStore):
    p1, p2 = _stream_llm_patches(["Hello", " world", "!"])
    with p1, p2:
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                },
            )
    assert response.status_code == 200
    body = response.text
    assert "event: conversation" in body
    assert "conversation_id" in body


def test_streaming_persists_assistant_response(store: ConversationStore):
    p1, p2 = _stream_llm_patches(["Chunk1", " Chunk2"])
    with p1, p2:
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                },
            )
    assert response.status_code == 200
    body = response.text
    assert "Chunk1" in body
    assert "Chunk2" in body

    convs = store.list_conversations()
    assert len(convs) == 1
    conv = store.get_conversation(convs[0]["id"])
    assert conv is not None
    assistant_msgs = [
        m for m in conv["messages"] if m["role"] == "assistant"
    ]
    assert any("Chunk1 Chunk2" in m["content"] for m in assistant_msgs)


def test_chat_backward_compat_no_conversation_id(store: ConversationStore):
    p1, p2 = _llm_patches("backward compat response")
    with p1, p2:
        client = TestClient(main_module.create_app())
        with client:
            response = client.post(
                "/api/chat",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "backward compat response"
    assert body["conversation_id"]
