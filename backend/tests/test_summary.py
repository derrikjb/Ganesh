"""Tests for the SummaryGenerationService (checkpoint + conversation summaries).

All LLM calls are mocked — no real API requests are made. Uses on-disk
SQLite + LanceDB under a temp directory so tests are fully isolated.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from ganesh_backend.embeddings import HashEmbedder  # noqa: E402
from ganesh_backend.services.conversations import ConversationStore  # noqa: E402
from ganesh_backend.services.summary import (  # noqa: E402
    SummaryGenerationService,
    get_summary_service,
    reset_summary_service,
    set_summary_service,
)
from ganesh_backend.services.summary_embeddings import SummaryEmbeddingStore  # noqa: E402


def _make_llm_response(content: str) -> Any:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.model = "test-model"
    return resp


def _add_messages(
    store: ConversationStore, conv_id: str, messages: list[tuple[str, str]]
) -> list[str]:
    ids: list[str] = []
    for role, content in messages:
        mid = store.add_message(conv_id, role=role, content=content)
        ids.append(mid)
    return ids


def _config_side_effect(key: str, default: Any = None) -> Any:
    defaults: dict[str, Any] = {
        "conversation_memory.enabled": True,
        "conversation_memory.min_messages_for_checkpoint": 2,
        "conversation_memory.summary_provider": None,
        "conversation_memory.summary_model": None,
    }
    return defaults.get(key, default)


@pytest.fixture
def conv_store(tmp_path: Path) -> ConversationStore:
    db_path = tmp_path / "conversations.db"
    lance_path = tmp_path / "lancedb"
    return ConversationStore(
        sqlite_path=str(db_path),
        lancedb_uri=str(lance_path),
        embedder=HashEmbedder(dimension=64),
        lancedb_collection=f"test_conv_{uuid.uuid4().hex[:8]}",
    )


@pytest.fixture
def emb_store(tmp_path: Path) -> SummaryEmbeddingStore:
    lance_path = tmp_path / "lancedb_summary"
    return SummaryEmbeddingStore(
        uri=str(lance_path),
        embedder=HashEmbedder(dimension=64),
    )


@pytest.fixture
def config() -> MagicMock:
    cfg = MagicMock()
    cfg.get_setting.side_effect = _config_side_effect
    return cfg


@pytest.fixture
def service(
    conv_store: ConversationStore,
    emb_store: SummaryEmbeddingStore,
    config: MagicMock,
) -> SummaryGenerationService:
    return SummaryGenerationService(
        conversation_store=conv_store,
        summary_embedding_store=emb_store,
        config=config,
    )


@patch("ganesh_backend.services.summary.llm_service")
def test_generate_checkpoint_no_prior_checkpoint(
    mock_llm: MagicMock,
    service: SummaryGenerationService,
    conv_store: ConversationStore,
) -> None:
    conv_id = conv_store.create_conversation(title="Test")
    msg_ids = _add_messages(
        conv_store,
        conv_id,
        [
            ("user", "What is Python?"),
            ("assistant", "Python is a programming language."),
            ("user", "Tell me more."),
            ("assistant", "It is widely used."),
        ],
    )
    mock_llm.chat_completion.return_value = _make_llm_response(
        "Discussed Python programming language basics."
    )
    mock_llm.DEFAULT_PROVIDER = "openai"
    mock_llm.DEFAULT_MODEL = "gpt-4o-mini"

    result = service.generate_checkpoint(conv_id)

    assert result is not None
    assert result["sequence_number"] == 0
    assert result["start_message_id"] == msg_ids[0]
    assert result["end_message_id"] == msg_ids[-1]
    assert result["summary"] == "Discussed Python programming language basics."
    assert result["conversation_id"] == conv_id

    mock_llm.chat_completion.assert_called_once()
    call_kwargs = mock_llm.chat_completion.call_args
    sent_messages = call_kwargs.kwargs["messages"]
    assert isinstance(sent_messages, list)
    assert sent_messages[0]["role"] == "system"


@patch("ganesh_backend.services.summary.llm_service")
def test_generate_checkpoint_with_prior_checkpoint(
    mock_llm: MagicMock,
    service: SummaryGenerationService,
    conv_store: ConversationStore,
) -> None:
    conv_id = conv_store.create_conversation(title="Test")
    first_batch = _add_messages(
        conv_store,
        conv_id,
        [("user", "Hello"), ("assistant", "Hi there")],
    )
    conv_store.create_checkpoint(
        conversation_id=conv_id,
        sequence_number=0,
        summary="Initial greeting.",
        start_message_id=first_batch[0],
        end_message_id=first_batch[-1],
    )

    second_batch = _add_messages(
        conv_store,
        conv_id,
        [("user", "What is Rust?"), ("assistant", "Rust is a systems language.")],
    )
    mock_llm.chat_completion.return_value = _make_llm_response(
        "Discussed Rust programming language."
    )
    mock_llm.DEFAULT_PROVIDER = "openai"
    mock_llm.DEFAULT_MODEL = "gpt-4o-mini"

    result = service.generate_checkpoint(conv_id)

    assert result is not None
    assert result["sequence_number"] == 1
    assert result["start_message_id"] == second_batch[0]
    assert result["end_message_id"] == second_batch[-1]
    assert result["summary"] == "Discussed Rust programming language."

    call_kwargs = mock_llm.chat_completion.call_args
    sent_messages = call_kwargs.kwargs["messages"]
    sent_content = " ".join(m.get("content", "") for m in sent_messages)
    assert "What is Rust?" in sent_content
    assert "Hello" not in sent_content


@patch("ganesh_backend.services.summary.llm_service")
def test_generate_checkpoint_skips_if_too_few_messages(
    mock_llm: MagicMock,
    service: SummaryGenerationService,
    conv_store: ConversationStore,
) -> None:
    conv_id = conv_store.create_conversation(title="Test")
    _add_messages(conv_store, conv_id, [("user", "Only one message")])
    mock_llm.chat_completion.return_value = _make_llm_response("summary")
    mock_llm.DEFAULT_PROVIDER = "openai"
    mock_llm.DEFAULT_MODEL = "gpt-4o-mini"

    result = service.generate_checkpoint(conv_id)

    assert result is None
    mock_llm.chat_completion.assert_not_called()


@patch("ganesh_backend.services.summary.llm_service")
def test_generate_checkpoint_creates_correct_sequence_and_ids(
    mock_llm: MagicMock,
    service: SummaryGenerationService,
    conv_store: ConversationStore,
) -> None:
    conv_id = conv_store.create_conversation(title="Test")
    msg_ids = _add_messages(
        conv_store,
        conv_id,
        [
            ("user", "msg1"),
            ("assistant", "msg2"),
            ("user", "msg3"),
            ("assistant", "msg4"),
        ],
    )
    conv_store.create_checkpoint(
        conversation_id=conv_id,
        sequence_number=5,
        summary="prior",
        start_message_id=msg_ids[0],
        end_message_id=msg_ids[1],
    )
    mock_llm.chat_completion.return_value = _make_llm_response("new summary")
    mock_llm.DEFAULT_PROVIDER = "openai"
    mock_llm.DEFAULT_MODEL = "gpt-4o-mini"

    result = service.generate_checkpoint(conv_id)

    assert result is not None
    assert result["sequence_number"] == 6
    assert result["start_message_id"] == msg_ids[2]
    assert result["end_message_id"] == msg_ids[3]


@patch("ganesh_backend.services.summary.llm_service")
def test_generate_checkpoint_indexes_in_embedding_store(
    mock_llm: MagicMock,
    service: SummaryGenerationService,
    conv_store: ConversationStore,
    emb_store: SummaryEmbeddingStore,
) -> None:
    conv_id = conv_store.create_conversation(title="Test")
    _add_messages(
        conv_store,
        conv_id,
        [("user", "Tell me about databases."), ("assistant", "Databases store data.")],
    )
    mock_llm.chat_completion.return_value = _make_llm_response(
        "Discussed databases and data storage."
    )
    mock_llm.DEFAULT_PROVIDER = "openai"
    mock_llm.DEFAULT_MODEL = "gpt-4o-mini"

    result = service.generate_checkpoint(conv_id)
    assert result is not None

    results = emb_store.search_checkpoint_summaries(
        query="databases",
        conversation_id=conv_id,
        limit=5,
    )
    assert len(results) == 1
    assert results[0].checkpoint_id == result["id"]
    assert results[0].conversation_id == conv_id
    assert results[0].sequence_number == result["sequence_number"]


@patch("ganesh_backend.services.summary.llm_service")
def test_generate_checkpoint_includes_prev_summary_in_prompt(
    mock_llm: MagicMock,
    service: SummaryGenerationService,
    conv_store: ConversationStore,
) -> None:
    conv_id = conv_store.create_conversation(title="Test")
    first_batch = _add_messages(
        conv_store,
        conv_id,
        [("user", "first"), ("assistant", "first reply")],
    )
    prev_summary = "Previously discussed first topic."
    conv_store.create_checkpoint(
        conversation_id=conv_id,
        sequence_number=0,
        summary=prev_summary,
        start_message_id=first_batch[0],
        end_message_id=first_batch[-1],
    )
    _add_messages(
        conv_store,
        conv_id,
        [("user", "second"), ("assistant", "second reply")],
    )
    mock_llm.chat_completion.return_value = _make_llm_response("second summary")
    mock_llm.DEFAULT_PROVIDER = "openai"
    mock_llm.DEFAULT_MODEL = "gpt-4o-mini"

    service.generate_checkpoint(conv_id)

    call_kwargs = mock_llm.chat_completion.call_args
    sent_messages = call_kwargs.kwargs["messages"]
    sent_content = " ".join(m.get("content", "") for m in sent_messages)
    assert prev_summary in sent_content


@patch("ganesh_backend.services.summary.llm_service")
def test_generate_checkpoint_returns_none_if_llm_fails(
    mock_llm: MagicMock,
    service: SummaryGenerationService,
    conv_store: ConversationStore,
) -> None:
    conv_id = conv_store.create_conversation(title="Test")
    _add_messages(
        conv_store,
        conv_id,
        [("user", "msg1"), ("assistant", "msg2")],
    )
    mock_llm.chat_completion.side_effect = RuntimeError("LLM down")
    mock_llm.LLMError = RuntimeError
    mock_llm.DEFAULT_PROVIDER = "openai"
    mock_llm.DEFAULT_MODEL = "gpt-4o-mini"

    result = service.generate_checkpoint(conv_id)

    assert result is None
    assert conv_store.get_checkpoint_count(conv_id) == 0


@patch("ganesh_backend.services.summary.llm_service")
def test_generate_checkpoint_uses_overridden_provider_model(
    mock_llm: MagicMock,
    conv_store: ConversationStore,
    emb_store: SummaryEmbeddingStore,
) -> None:
    cfg = MagicMock()
    cfg.get_setting.side_effect = lambda key, default=None: {
        "conversation_memory.enabled": True,
        "conversation_memory.min_messages_for_checkpoint": 2,
        "conversation_memory.summary_provider": "anthropic",
        "conversation_memory.summary_model": "claude-3-5-sonnet-20240620",
    }.get(key, default)

    svc = SummaryGenerationService(
        conversation_store=conv_store,
        summary_embedding_store=emb_store,
        config=cfg,
    )
    conv_id = conv_store.create_conversation(title="Test")
    _add_messages(
        conv_store,
        conv_id,
        [("user", "msg1"), ("assistant", "msg2")],
    )
    mock_llm.chat_completion.return_value = _make_llm_response("summary")
    mock_llm.DEFAULT_PROVIDER = "openai"
    mock_llm.DEFAULT_MODEL = "gpt-4o-mini"

    svc.generate_checkpoint(conv_id)

    call_kwargs = mock_llm.chat_completion.call_args
    assert call_kwargs.kwargs["provider"] == "anthropic"
    assert call_kwargs.kwargs["model"] == "claude-3-5-sonnet-20240620"


@patch("ganesh_backend.services.summary.llm_service")
def test_generate_conversation_summary_combines_checkpoints_and_recent(
    mock_llm: MagicMock,
    service: SummaryGenerationService,
    conv_store: ConversationStore,
) -> None:
    conv_id = conv_store.create_conversation(title="Test")
    first_batch = _add_messages(
        conv_store,
        conv_id,
        [("user", "topic A"), ("assistant", "reply A")],
    )
    conv_store.create_checkpoint(
        conversation_id=conv_id,
        sequence_number=0,
        summary="Checkpoint A summary.",
        start_message_id=first_batch[0],
        end_message_id=first_batch[-1],
    )
    _add_messages(
        conv_store,
        conv_id,
        [("user", "topic B recent"), ("assistant", "reply B recent")],
    )
    mock_llm.chat_completion.return_value = _make_llm_response(
        "Full conversation summary."
    )
    mock_llm.DEFAULT_PROVIDER = "openai"
    mock_llm.DEFAULT_MODEL = "gpt-4o-mini"

    result = service.generate_conversation_summary(conv_id)

    assert result == "Full conversation summary."
    call_kwargs = mock_llm.chat_completion.call_args
    sent_messages = call_kwargs.kwargs["messages"]
    sent_content = " ".join(m.get("content", "") for m in sent_messages)
    assert "Checkpoint A summary." in sent_content
    assert "topic B recent" in sent_content

    conv = conv_store.get_conversation(conv_id)
    assert conv is not None
    assert conv["status"] == "closed"
    assert conv["summary"] == "Full conversation summary."


@patch("ganesh_backend.services.summary.llm_service")
def test_generate_conversation_summary_no_checkpoints_summarizes_all(
    mock_llm: MagicMock,
    service: SummaryGenerationService,
    conv_store: ConversationStore,
) -> None:
    conv_id = conv_store.create_conversation(title="Test")
    _add_messages(
        conv_store,
        conv_id,
        [
            ("user", "direct msg 1"),
            ("assistant", "direct reply 1"),
            ("user", "direct msg 2"),
            ("assistant", "direct reply 2"),
        ],
    )
    mock_llm.chat_completion.return_value = _make_llm_response(
        "Direct conversation summary."
    )
    mock_llm.DEFAULT_PROVIDER = "openai"
    mock_llm.DEFAULT_MODEL = "gpt-4o-mini"

    result = service.generate_conversation_summary(conv_id)

    assert result == "Direct conversation summary."
    call_kwargs = mock_llm.chat_completion.call_args
    sent_messages = call_kwargs.kwargs["messages"]
    sent_content = " ".join(m.get("content", "") for m in sent_messages)
    assert "direct msg 1" in sent_content
    assert "direct msg 2" in sent_content


@patch("ganesh_backend.services.summary.llm_service")
def test_generate_conversation_summary_stores_and_marks_closed(
    mock_llm: MagicMock,
    service: SummaryGenerationService,
    conv_store: ConversationStore,
) -> None:
    conv_id = conv_store.create_conversation(title="Test")
    _add_messages(
        conv_store,
        conv_id,
        [("user", "msg"), ("assistant", "reply")],
    )
    mock_llm.chat_completion.return_value = _make_llm_response("Stored summary.")
    mock_llm.DEFAULT_PROVIDER = "openai"
    mock_llm.DEFAULT_MODEL = "gpt-4o-mini"

    service.generate_conversation_summary(conv_id)

    conv = conv_store.get_conversation(conv_id)
    assert conv is not None
    assert conv["status"] == "closed"
    assert conv["closed_at"] is not None
    assert conv["summary"] == "Stored summary."


@patch("ganesh_backend.services.summary.llm_service")
def test_generate_conversation_summary_indexes_in_embedding_store(
    mock_llm: MagicMock,
    service: SummaryGenerationService,
    conv_store: ConversationStore,
    emb_store: SummaryEmbeddingStore,
) -> None:
    conv_id = conv_store.create_conversation(title="Test")
    _add_messages(
        conv_store,
        conv_id,
        [("user", "msg"), ("assistant", "reply")],
    )
    mock_llm.chat_completion.return_value = _make_llm_response(
        "Indexed conversation summary."
    )
    mock_llm.DEFAULT_PROVIDER = "openai"
    mock_llm.DEFAULT_MODEL = "gpt-4o-mini"

    service.generate_conversation_summary(conv_id)

    results = emb_store.search_conversation_summaries(
        query="conversation",
        limit=5,
    )
    assert len(results) == 1
    assert results[0].conversation_id == conv_id
    assert results[0].summary == "Indexed conversation summary."


@patch("ganesh_backend.services.summary.llm_service")
def test_generate_conversation_summary_returns_none_and_closes_on_llm_failure(
    mock_llm: MagicMock,
    service: SummaryGenerationService,
    conv_store: ConversationStore,
) -> None:
    conv_id = conv_store.create_conversation(title="Test")
    _add_messages(
        conv_store,
        conv_id,
        [("user", "msg"), ("assistant", "reply")],
    )
    mock_llm.chat_completion.side_effect = RuntimeError("LLM down")
    mock_llm.LLMError = RuntimeError
    mock_llm.DEFAULT_PROVIDER = "openai"
    mock_llm.DEFAULT_MODEL = "gpt-4o-mini"

    result = service.generate_conversation_summary(conv_id)

    assert result is None
    conv = conv_store.get_conversation(conv_id)
    assert conv is not None
    assert conv["status"] == "closed"
    assert conv["summary"] is None


def test_singleton_get_set_reset() -> None:
    reset_summary_service()
    svc = get_summary_service()
    assert isinstance(svc, SummaryGenerationService)

    custom = MagicMock(spec=SummaryGenerationService)
    set_summary_service(custom)
    assert get_summary_service() is custom

    reset_summary_service()
    new_svc = get_summary_service()
    assert new_svc is not custom
    assert isinstance(new_svc, SummaryGenerationService)

    reset_summary_service()
