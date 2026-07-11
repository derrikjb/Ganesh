"""Tests for the conversation history service (SQLite + LanceDB semantic search).

Uses a temporary on-disk SQLite database and in-memory LanceDB so tests are
isolated and require no external services or model downloads.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from ganesh_backend.embeddings import HashEmbedder  # noqa: E402
from ganesh_backend.services.conversations import ConversationStore  # noqa: E402


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


# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------


def test_migration_adds_columns_and_checkpoints_table(tmp_path: Path) -> None:
    """An existing database without the new columns/table is migrated on open."""
    db_path = tmp_path / "conversations.db"
    lance_path = tmp_path / "lancedb"

    # Create a legacy database with the OLD schema (no summary/status/closed_at,
    # no checkpoints table) and insert a row.
    legacy_conn = sqlite3.connect(str(db_path))
    legacy_conn.execute(
        """
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            profile_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    legacy_conn.execute(
        """
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
        """
    )
    legacy_conn.execute(
        "INSERT INTO conversations (id, title, profile_id, created_at, updated_at) "
        "VALUES (?, ?, NULL, ?, ?)",
        ("legacy-1", "Legacy", "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00"),
    )
    legacy_conn.commit()
    legacy_conn.close()

    # Opening the store triggers migration.
    store = ConversationStore(
        sqlite_path=str(db_path),
        lancedb_uri=str(lance_path),
        embedder=HashEmbedder(dimension=64),
        lancedb_collection=f"test_conv_embeddings_{uuid.uuid4().hex[:8]}",
    )

    # Verify new columns exist on conversations table.
    conn = sqlite3.connect(str(db_path))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(conversations)").fetchall()}
    conn.close()
    assert "summary" in cols
    assert "status" in cols
    assert "closed_at" in cols

    # Verify checkpoints table exists.
    conn = sqlite3.connect(str(db_path))
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert "checkpoints" in tables

    # Verify the legacy row is intact and got the default status.
    conv = store.get_conversation("legacy-1")
    assert conv is not None
    assert conv["title"] == "Legacy"
    assert conv["status"] == "active"
    assert conv["summary"] is None
    assert conv["closed_at"] is None

    # Idempotency: re-opening the store should not fail.
    store2 = ConversationStore(
        sqlite_path=str(db_path),
        lancedb_uri=str(lance_path),
        embedder=HashEmbedder(dimension=64),
        lancedb_collection=f"test_conv_embeddings_{uuid.uuid4().hex[:8]}",
    )
    conv2 = store2.get_conversation("legacy-1")
    assert conv2 is not None
    assert conv2["status"] == "active"


# ---------------------------------------------------------------------------
# Conversation lifecycle methods
# ---------------------------------------------------------------------------


def test_set_conversation_summary(store: ConversationStore) -> None:
    conv_id = store.create_conversation(title="Summarize Me")
    store.set_conversation_summary(conv_id, "A short summary of the chat.")

    conv = store.get_conversation(conv_id)
    assert conv is not None
    assert conv["summary"] == "A short summary of the chat."
    assert conv["status"] == "closed"
    assert conv["closed_at"] is not None


def test_get_conversation_summary(store: ConversationStore) -> None:
    conv_id = store.create_conversation()
    assert store.get_conversation_summary(conv_id) is None

    store.set_conversation_summary(conv_id, "The summary text.")
    assert store.get_conversation_summary(conv_id) == "The summary text."


def test_close_conversation(store: ConversationStore) -> None:
    conv_id = store.create_conversation()
    assert store.close_conversation(conv_id) is True

    conv = store.get_conversation(conv_id)
    assert conv is not None
    assert conv["status"] == "closed"
    assert conv["closed_at"] is not None
    assert conv["summary"] is None  # close does not set a summary

    # Closing a non-existent conversation returns False.
    assert store.close_conversation("does-not-exist") is False


def test_get_conversation_status(store: ConversationStore) -> None:
    conv_id = store.create_conversation()
    assert store.get_conversation_status(conv_id) == "active"

    store.close_conversation(conv_id)
    assert store.get_conversation_status(conv_id) == "closed"

    assert store.get_conversation_status("nonexistent") is None


def test_get_last_message_timestamp(store: ConversationStore) -> None:
    conv_id = store.create_conversation()
    assert store.get_last_message_timestamp(conv_id) is None

    store.add_message(conv_id, role="user", content="first")
    ts1 = store.get_last_message_timestamp(conv_id)
    assert ts1 is not None

    store.add_message(conv_id, role="assistant", content="second")
    ts2 = store.get_last_message_timestamp(conv_id)
    assert ts2 is not None
    assert ts2 >= ts1

    assert store.get_last_message_timestamp("nonexistent") is None


def test_get_active_conversation(store: ConversationStore) -> None:
    # No conversations yet.
    assert store.get_active_conversation(profile_id=None) is None

    c1 = store.create_conversation(profile_id="p1", title="First")
    store.add_message(c1, role="user", content="hello")

    c2 = store.create_conversation(profile_id="p1", title="Second")
    store.add_message(c2, role="user", content="hi again")

    # Most recent active conversation for p1 is c2.
    active = store.get_active_conversation(profile_id="p1")
    assert active is not None
    assert active["id"] == c2

    # Close c2; now c1 is the most recent active.
    store.close_conversation(c2)
    active = store.get_active_conversation(profile_id="p1")
    assert active is not None
    assert active["id"] == c1

    # Close c1; no active conversation left.
    store.close_conversation(c1)
    assert store.get_active_conversation(profile_id="p1") is None

    # Different profile.
    assert store.get_active_conversation(profile_id="other") is None


def test_get_active_conversation_no_profile(store: ConversationStore) -> None:
    c1 = store.create_conversation(profile_id=None, title="No Profile")
    store.add_message(c1, role="user", content="msg")

    active = store.get_active_conversation(profile_id=None)
    assert active is not None
    assert active["id"] == c1


# ---------------------------------------------------------------------------
# Checkpoint CRUD
# ---------------------------------------------------------------------------


def test_create_checkpoint(store: ConversationStore) -> None:
    conv_id = store.create_conversation()
    m1 = store.add_message(conv_id, role="user", content="hello")
    m2 = store.add_message(conv_id, role="assistant", content="hi there")

    cp_id = store.create_checkpoint(
        conversation_id=conv_id,
        sequence_number=0,
        summary="User greeted the assistant.",
        start_message_id=m1,
        end_message_id=m2,
    )
    assert cp_id

    cp = store.get_checkpoint(conv_id, sequence_number=0)
    assert cp is not None
    assert cp["id"] == cp_id
    assert cp["conversation_id"] == conv_id
    assert cp["sequence_number"] == 0
    assert cp["summary"] == "User greeted the assistant."
    assert cp["start_message_id"] == m1
    assert cp["end_message_id"] == m2
    assert cp["created_at"]


def test_get_checkpoints_ordered(store: ConversationStore) -> None:
    conv_id = store.create_conversation()
    store.create_checkpoint(conv_id, 2, "third", None, None)
    store.create_checkpoint(conv_id, 0, "first", None, None)
    store.create_checkpoint(conv_id, 1, "second", None, None)

    cps = store.get_checkpoints(conv_id)
    assert len(cps) == 3
    assert [c["sequence_number"] for c in cps] == [0, 1, 2]
    assert [c["summary"] for c in cps] == ["first", "second", "third"]


def test_get_latest_checkpoint(store: ConversationStore) -> None:
    conv_id = store.create_conversation()
    assert store.get_latest_checkpoint(conv_id) is None

    store.create_checkpoint(conv_id, 0, "c0", None, None)
    store.create_checkpoint(conv_id, 1, "c1", None, None)
    store.create_checkpoint(conv_id, 2, "c2", None, None)

    latest = store.get_latest_checkpoint(conv_id)
    assert latest is not None
    assert latest["sequence_number"] == 2
    assert latest["summary"] == "c2"


def test_get_checkpoint_count(store: ConversationStore) -> None:
    conv_id = store.create_conversation()
    assert store.get_checkpoint_count(conv_id) == 0

    store.create_checkpoint(conv_id, 0, "c0", None, None)
    assert store.get_checkpoint_count(conv_id) == 1

    store.create_checkpoint(conv_id, 1, "c1", None, None)
    assert store.get_checkpoint_count(conv_id) == 2


def test_get_messages_between(store: ConversationStore) -> None:
    conv_id = store.create_conversation()
    m0 = store.add_message(conv_id, role="user", content="m0")
    m1 = store.add_message(conv_id, role="assistant", content="m1")
    m2 = store.add_message(conv_id, role="user", content="m2")
    m3 = store.add_message(conv_id, role="assistant", content="m3")
    m4 = store.add_message(conv_id, role="user", content="m4")

    # Full range (None boundaries) returns all messages.
    all_msgs = store.get_messages_between(conv_id, None, None)
    assert [m["id"] for m in all_msgs] == [m0, m1, m2, m3, m4]

    # From beginning to m2 (inclusive).
    seg = store.get_messages_between(conv_id, None, m2)
    assert [m["id"] for m in seg] == [m0, m1, m2]

    # From m1 to m3 (inclusive).
    seg = store.get_messages_between(conv_id, m1, m3)
    assert [m["id"] for m in seg] == [m1, m2, m3]

    # From m2 to end.
    seg = store.get_messages_between(conv_id, m2, None)
    assert [m["id"] for m in seg] == [m2, m3, m4]

    # Single message.
    seg = store.get_messages_between(conv_id, m2, m2)
    assert [m["id"] for m in seg] == [m2]


def test_get_messages_since_checkpoint(store: ConversationStore) -> None:
    conv_id = store.create_conversation()
    m0 = store.add_message(conv_id, role="user", content="m0")
    m1 = store.add_message(conv_id, role="assistant", content="m1")
    m2 = store.add_message(conv_id, role="user", content="m2")
    m3 = store.add_message(conv_id, role="assistant", content="m3")
    m4 = store.add_message(conv_id, role="user", content="m4")

    # Checkpoint covering m0..m1.
    store.create_checkpoint(conv_id, 0, "first segment", m0, m1)

    # Messages since checkpoint 0 = messages after m1 = [m2, m3, m4].
    since = store.get_messages_since_checkpoint(conv_id, 0)
    assert [m["id"] for m in since] == [m2, m3, m4]

    # Checkpoint covering m2..m3.
    store.create_checkpoint(conv_id, 1, "second segment", m2, m3)

    # Messages since checkpoint 1 = messages after m3 = [m4].
    since = store.get_messages_since_checkpoint(conv_id, 1)
    assert [m["id"] for m in since] == [m4]

    # Non-existent checkpoint sequence returns empty list.
    assert store.get_messages_since_checkpoint(conv_id, 99) == []


def test_delete_checkpoint(store: ConversationStore) -> None:
    conv_id = store.create_conversation()
    store.create_checkpoint(conv_id, 0, "c0", None, None)
    store.create_checkpoint(conv_id, 1, "c1", None, None)

    assert store.get_checkpoint_count(conv_id) == 2

    deleted = store.delete_checkpoint(conv_id, 0)
    assert deleted is True
    assert store.get_checkpoint_count(conv_id) == 1
    assert store.get_checkpoint(conv_id, 0) is None
    assert store.get_checkpoint(conv_id, 1) is not None

    # Deleting non-existent checkpoint returns False.
    assert store.delete_checkpoint(conv_id, 99) is False
    assert store.delete_conversation("nonexistent") is False


# ---------------------------------------------------------------------------
# Updated existing methods
# ---------------------------------------------------------------------------


def test_get_conversation_includes_new_fields_and_checkpoints(
    store: ConversationStore,
) -> None:
    conv_id = store.create_conversation()
    store.add_message(conv_id, role="user", content="hi")

    conv = store.get_conversation(conv_id)
    assert conv is not None
    assert conv["summary"] is None
    assert conv["status"] == "active"
    assert conv["closed_at"] is None
    assert conv["checkpoints"] == []

    # Add a checkpoint and verify it appears.
    store.create_checkpoint(conv_id, 0, "a checkpoint", None, None)
    conv = store.get_conversation(conv_id)
    assert conv is not None
    assert len(conv["checkpoints"]) == 1
    assert conv["checkpoints"][0]["summary"] == "a checkpoint"
    assert conv["checkpoints"][0]["sequence_number"] == 0


def test_list_conversations_includes_new_fields(store: ConversationStore) -> None:
    conv_id = store.create_conversation(title="With Summary")
    store.add_message(conv_id, role="user", content="hello")

    long_summary = "x" * 200
    store.set_conversation_summary(conv_id, long_summary)

    convs = store.list_conversations()
    assert len(convs) == 1
    c = convs[0]
    assert c["id"] == conv_id
    assert c["status"] == "closed"
    # Summary truncated to 100 chars.
    assert c["summary"] == "x" * 100
    assert len(c["summary"]) == 100


def test_existing_conversation_defaults(store: ConversationStore) -> None:
    """Conversations created without summary/status return sensible defaults."""
    conv_id = store.create_conversation()
    conv = store.get_conversation(conv_id)
    assert conv is not None
    assert conv["summary"] is None
    assert conv["status"] == "active"
    assert conv["closed_at"] is None
    assert conv["checkpoints"] == []


def test_create_conversation_with_status(store: ConversationStore) -> None:
    conv_id = store.create_conversation(status="closed")
    conv = store.get_conversation(conv_id)
    assert conv is not None
    assert conv["status"] == "closed"


def test_delete_conversation_cascades_to_checkpoints(
    store: ConversationStore,
) -> None:
    conv_id = store.create_conversation()
    store.add_message(conv_id, role="user", content="hi")
    store.create_checkpoint(conv_id, 0, "cp0", None, None)
    store.create_checkpoint(conv_id, 1, "cp1", None, None)

    assert store.get_checkpoint_count(conv_id) == 2

    deleted = store.delete_conversation(conv_id)
    assert deleted is True

    # Checkpoints should be gone (cascade).
    assert store.get_checkpoints(conv_id) == []
    assert store.get_checkpoint_count(conv_id) == 0


# ---------------------------------------------------------------------------
# Router endpoint tests (close + checkpoints)
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock, patch  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

import main as main_module  # noqa: E402
from ganesh_backend.routers import conversations as conversations_router  # noqa: E402


@pytest.fixture
def app_client(store: ConversationStore):
    conversations_router.set_conversation_service(store)
    app = main_module.create_app()
    with TestClient(app) as client:
        yield client
    conversations_router.reset_conversation_service()


def _mock_summary_service(
    checkpoint_result=None, conversation_summary="conv summary", store=None
):
    svc = MagicMock()
    svc.generate_checkpoint.return_value = checkpoint_result

    def _conv_summary(conv_id):
        if store is not None:
            store.set_conversation_summary(conv_id, conversation_summary)
        return conversation_summary

    svc.generate_conversation_summary.side_effect = _conv_summary
    return svc


def test_close_endpoint_generates_summary_and_marks_closed(
    app_client: TestClient, store: ConversationStore
):
    conv_id = store.create_conversation()
    store.add_message(conv_id, role="user", content="hello")
    store.add_message(conv_id, role="assistant", content="hi")

    mock_svc = _mock_summary_service(
        checkpoint_result={"sequence_number": 0},
        conversation_summary="final summary",
        store=store,
    )
    with patch(
        "ganesh_backend.services.summary.get_summary_service",
        return_value=mock_svc,
    ):
        response = app_client.post(f"/api/conversations/{conv_id}/close")

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == conv_id
    assert body["summary"] == "final summary"
    assert body["status"] == "closed"
    assert body["checkpoint_count"] >= 0
    mock_svc.generate_checkpoint.assert_called_once_with(conv_id)
    mock_svc.generate_conversation_summary.assert_called_once_with(conv_id)


def test_close_endpoint_generates_final_checkpoint(
    app_client: TestClient, store: ConversationStore
):
    conv_id = store.create_conversation()
    m1 = store.add_message(conv_id, role="user", content="msg1")
    store.add_message(conv_id, role="assistant", content="reply1")
    store.create_checkpoint(conv_id, 0, "first cp", m1, m1)

    mock_svc = _mock_summary_service(
        checkpoint_result={"sequence_number": 1},
        conversation_summary="conv summary",
        store=store,
    )
    with patch(
        "ganesh_backend.services.summary.get_summary_service",
        return_value=mock_svc,
    ):
        response = app_client.post(f"/api/conversations/{conv_id}/close")

    assert response.status_code == 200
    mock_svc.generate_checkpoint.assert_called_once_with(conv_id)


def test_close_endpoint_already_closed_returns_existing_summary(
    app_client: TestClient, store: ConversationStore
):
    conv_id = store.create_conversation()
    store.add_message(conv_id, role="user", content="msg")
    store.set_conversation_summary(conv_id, "existing summary")

    mock_svc = _mock_summary_service()
    with patch(
        "ganesh_backend.services.summary.get_summary_service",
        return_value=mock_svc,
    ):
        response = app_client.post(f"/api/conversations/{conv_id}/close")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "existing summary"
    assert body["status"] == "closed"
    mock_svc.generate_checkpoint.assert_not_called()
    mock_svc.generate_conversation_summary.assert_not_called()


def test_close_endpoint_nonexistent_returns_404(app_client: TestClient):
    response = app_client.post(
        "/api/conversations/nonexistent-id/close"
    )
    assert response.status_code == 404


def test_checkpoints_endpoint_returns_all_in_order(
    app_client: TestClient, store: ConversationStore
):
    conv_id = store.create_conversation()
    store.create_checkpoint(conv_id, 2, "third", None, None)
    store.create_checkpoint(conv_id, 0, "first", None, None)
    store.create_checkpoint(conv_id, 1, "second", None, None)

    response = app_client.get(f"/api/conversations/{conv_id}/checkpoints")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    assert [c["sequence_number"] for c in body] == [0, 1, 2]
    assert [c["summary"] for c in body] == ["first", "second", "third"]


def test_checkpoints_endpoint_nonexistent_returns_404(
    app_client: TestClient
):
    response = app_client.get(
        "/api/conversations/nonexistent-id/checkpoints"
    )
    assert response.status_code == 404


def test_checkpoint_messages_endpoint_returns_segment(
    app_client: TestClient, store: ConversationStore
):
    conv_id = store.create_conversation()
    m0 = store.add_message(conv_id, role="user", content="m0")
    m1 = store.add_message(conv_id, role="assistant", content="m1")
    m2 = store.add_message(conv_id, role="user", content="m2")
    m3 = store.add_message(conv_id, role="assistant", content="m3")

    store.create_checkpoint(conv_id, 0, "first segment", m0, m1)
    store.create_checkpoint(conv_id, 1, "second segment", m2, m3)

    response = app_client.get(
        f"/api/conversations/{conv_id}/checkpoints/0/messages"
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert [m["content"] for m in body] == ["m0", "m1"]

    response = app_client.get(
        f"/api/conversations/{conv_id}/checkpoints/1/messages"
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert [m["content"] for m in body] == ["m2", "m3"]


def test_checkpoint_messages_endpoint_nonexistent_checkpoint_404(
    app_client: TestClient, store: ConversationStore
):
    conv_id = store.create_conversation()
    store.add_message(conv_id, role="user", content="msg")

    response = app_client.get(
        f"/api/conversations/{conv_id}/checkpoints/99/messages"
    )
    assert response.status_code == 404
