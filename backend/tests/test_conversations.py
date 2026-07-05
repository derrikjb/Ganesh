"""Tests for the conversation history service (SQLite + LanceDB semantic search).

Uses a temporary on-disk SQLite database and in-memory LanceDB so tests are
isolated and require no external services or model downloads.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from ganesh_backend.embeddings import HashEmbedder
from ganesh_backend.services.conversations import ConversationStore


@pytest.fixture
def store(tmp_path: Path) -> ConversationStore:
    db_path = tmp_path / "conversations.db"
    lance_path = tmp_path / "lancedb"
    return ConversationStore(
        sqlite_path=str(db_path),
        lancedb_uri=str(lance_path),
        embedder=HashEmbedder(dimension=64),
        lancedb_collection=f"test_conv_embeddings_{uuid.uuid4().hex[:8]}",
    )


def test_create_conversation(store: ConversationStore) -> None:
    conv_id = store.create_conversation(title="My Chat")
    assert conv_id

    conv = store.get_conversation(conv_id)
    assert conv is not None
    assert conv["title"] == "My Chat"
    assert conv["messages"] == []
    assert conv["message_count"] == 0


def test_add_message_and_auto_title(store: ConversationStore) -> None:
    conv_id = store.create_conversation()  # no title
    long_text = "How do I configure the LLM router for multiple providers in Ganesh?"
    store.add_message(conv_id, role="user", content=long_text)
    store.add_message(conv_id, role="assistant", content="You can configure...")

    conv = store.get_conversation(conv_id)
    assert conv is not None
    # Auto-title from first 50 chars of first user message
    assert conv["title"] == long_text[:50]
    assert conv["message_count"] == 2
    assert len(conv["messages"]) == 2
    assert conv["messages"][0]["role"] == "user"
    assert conv["messages"][0]["content"] == long_text
    assert conv["messages"][1]["role"] == "assistant"


def test_search_conversations(store: ConversationStore) -> None:
    c1 = store.create_conversation()
    store.add_message(c1, role="user", content="Tell me about Python programming language.")
    store.add_message(c1, role="assistant", content="Python is a high-level language.")

    c2 = store.create_conversation()
    store.add_message(c2, role="user", content="What is the weather like today?")
    store.add_message(c2, role="assistant", content="It is sunny.")

    c3 = store.create_conversation()
    store.add_message(c3, role="user", content="How do I bake chocolate chip cookies?")
    store.add_message(c3, role="assistant", content="Mix flour, sugar, and chocolate.")

    results = store.search_conversations(query="programming language python", limit=3)
    assert len(results) >= 1
    # The Python conversation must be among the relevant results. The
    # HashEmbedder is deterministic but not truly semantic (it hashes
    # substrings), so we assert membership rather than strict rank-1.
    result_ids = [r["id"] for r in results]
    assert c1 in result_ids
    python_conv = next(r for r in results if r["id"] == c1)
    assert any("python" in m["content"].lower() for m in python_conv["messages"])


def test_export_json(store: ConversationStore) -> None:
    conv_id = store.create_conversation(title="Export Test")
    store.add_message(conv_id, role="user", content="Hello there.")
    store.add_message(conv_id, role="assistant", content="Hi! How can I help?")

    exported = store.export_conversation(conv_id, format="json")
    data = json.loads(exported)
    assert data["id"] == conv_id
    assert data["title"] == "Export Test"
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][0]["content"] == "Hello there."
    assert data["messages"][1]["role"] == "assistant"
    assert "created_at" in data
    assert "updated_at" in data


def test_export_markdown(store: ConversationStore) -> None:
    conv_id = store.create_conversation(title="Markdown Export")
    store.add_message(conv_id, role="user", content="What is 2+2?")
    store.add_message(conv_id, role="assistant", content="2+2 equals 4.")

    exported = store.export_conversation(conv_id, format="markdown")
    assert isinstance(exported, str)
    assert "# Markdown Export" in exported
    assert "**User**" in exported
    assert "What is 2+2?" in exported
    assert "**Assistant**" in exported
    assert "2+2 equals 4." in exported


def test_delete_conversation(store: ConversationStore) -> None:
    conv_id = store.create_conversation(title="To Delete")
    store.add_message(conv_id, role="user", content="Goodbye.")
    store.add_message(conv_id, role="assistant", content="See you later.")

    # Verify exists
    assert store.get_conversation(conv_id) is not None

    deleted = store.delete_conversation(conv_id)
    assert deleted is True

    # Verify gone
    assert store.get_conversation(conv_id) is None
    assert store.delete_conversation(conv_id) is False

    # Verify not in list
    convs = store.list_conversations()
    assert all(c["id"] != conv_id for c in convs)


def test_list_conversations(store: ConversationStore) -> None:
    c1 = store.create_conversation(title="First")
    store.add_message(c1, role="user", content="msg1")
    c2 = store.create_conversation(title="Second")
    store.add_message(c2, role="user", content="msg2")
    store.add_message(c2, role="assistant", content="reply2")

    convs = store.list_conversations()
    assert len(convs) == 2
    titles = {c["title"] for c in convs}
    assert "First" in titles
    assert "Second" in titles
    counts = {c["id"]: c["message_count"] for c in convs}
    assert counts[c1] == 1
    assert counts[c2] == 2
