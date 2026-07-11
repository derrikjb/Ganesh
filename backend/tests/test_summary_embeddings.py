"""Tests for the SummaryEmbeddingStore (LanceDB-backed summary embeddings).

Uses HashEmbedder (deterministic, no model downloads) and on-disk LanceDB
under a temp directory so tests are fully isolated.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from ganesh_backend.embeddings import HashEmbedder  # noqa: E402
from ganesh_backend.services.summary_embeddings import (  # noqa: E402
    CheckpointSearchResult,
    ConversationSearchResult,
    SummaryEmbeddingStore,
)


@pytest.fixture
def store(tmp_path: Path) -> SummaryEmbeddingStore:
    lance_path = tmp_path / "lancedb"
    return SummaryEmbeddingStore(
        uri=str(lance_path),
        embedder=HashEmbedder(dimension=64),
    )


def test_index_checkpoint_summary_stores_embedding(
    store: SummaryEmbeddingStore,
) -> None:
    checkpoint_id = f"cp-{uuid.uuid4().hex[:8]}"
    conversation_id = f"conv-{uuid.uuid4().hex[:8]}"
    summary = "Discussed Python web frameworks and their trade-offs."
    metadata = {
        "start_message_id": "msg-1",
        "end_message_id": "msg-5",
        "created_at": "2025-01-01T10:00:00Z",
    }

    store.index_checkpoint_summary(
        checkpoint_id=checkpoint_id,
        conversation_id=conversation_id,
        sequence_number=0,
        summary=summary,
        metadata=metadata,
    )

    results = store.search_checkpoint_summaries(
        query=summary,
        conversation_id=conversation_id,
        limit=5,
    )
    assert len(results) == 1
    r = results[0]
    assert isinstance(r, CheckpointSearchResult)
    assert r.checkpoint_id == checkpoint_id
    assert r.conversation_id == conversation_id
    assert r.sequence_number == 0
    assert r.summary == summary
    assert r.score > 0.0
    assert r.metadata["start_message_id"] == "msg-1"
    assert r.metadata["end_message_id"] == "msg-5"
    assert r.metadata["created_at"] == "2025-01-01T10:00:00Z"


def test_search_checkpoint_summaries_ranked_and_filtered(
    store: SummaryEmbeddingStore,
) -> None:
    conv_a = f"conv-{uuid.uuid4().hex[:8]}"
    conv_b = f"conv-{uuid.uuid4().hex[:8]}"

    matching_summary = "Setting up a PostgreSQL database for the project."
    store.index_checkpoint_summary(
        checkpoint_id="cp-a-1",
        conversation_id=conv_a,
        sequence_number=0,
        summary=matching_summary,
        metadata={"start_message_id": "m1", "end_message_id": "m3",
                  "created_at": "2025-01-01T09:00:00Z"},
    )
    store.index_checkpoint_summary(
        checkpoint_id="cp-a-2",
        conversation_id=conv_a,
        sequence_number=1,
        summary="Cooking pasta recipes for dinner.",
        metadata={"start_message_id": "m4", "end_message_id": "m6",
                  "created_at": "2025-01-01T10:00:00Z"},
    )
    store.index_checkpoint_summary(
        checkpoint_id="cp-b-1",
        conversation_id=conv_b,
        sequence_number=0,
        summary=matching_summary,
        metadata={"start_message_id": "m1", "end_message_id": "m2",
                  "created_at": "2025-01-01T09:00:00Z"},
    )

    results = store.search_checkpoint_summaries(
        query=matching_summary,
        conversation_id=conv_a,
        limit=5,
    )
    assert all(r.conversation_id == conv_a for r in results)
    assert len(results) == 2
    assert results[0].checkpoint_id == "cp-a-1"
    assert results[0].score >= results[1].score


def test_search_checkpoint_summaries_empty_conversation(
    store: SummaryEmbeddingStore,
) -> None:
    conv_a = f"conv-{uuid.uuid4().hex[:8]}"
    conv_empty = f"conv-{uuid.uuid4().hex[:8]}"

    store.index_checkpoint_summary(
        checkpoint_id="cp-a-1",
        conversation_id=conv_a,
        sequence_number=0,
        summary="Some summary text here.",
        metadata={"created_at": "2025-01-01T09:00:00Z"},
    )

    results = store.search_checkpoint_summaries(
        query="anything",
        conversation_id=conv_empty,
        limit=5,
    )
    assert results == []


def test_delete_checkpoint_summary(store: SummaryEmbeddingStore) -> None:
    checkpoint_id = f"cp-{uuid.uuid4().hex[:8]}"
    conversation_id = f"conv-{uuid.uuid4().hex[:8]}"
    summary = "A checkpoint about machine learning models."

    store.index_checkpoint_summary(
        checkpoint_id=checkpoint_id,
        conversation_id=conversation_id,
        sequence_number=0,
        summary=summary,
        metadata={"created_at": "2025-01-01T09:00:00Z"},
    )

    results = store.search_checkpoint_summaries(
        query=summary, conversation_id=conversation_id, limit=5,
    )
    assert len(results) == 1

    store.delete_checkpoint_summary(checkpoint_id)
    results = store.search_checkpoint_summaries(
        query=summary, conversation_id=conversation_id, limit=5,
    )
    assert results == []


def test_delete_conversation_checkpoints(store: SummaryEmbeddingStore) -> None:
    conv_a = f"conv-{uuid.uuid4().hex[:8]}"
    conv_b = f"conv-{uuid.uuid4().hex[:8]}"

    store.index_checkpoint_summary(
        checkpoint_id="cp-a-1", conversation_id=conv_a, sequence_number=0,
        summary="First checkpoint.", metadata={"created_at": "t1"},
    )
    store.index_checkpoint_summary(
        checkpoint_id="cp-a-2", conversation_id=conv_a, sequence_number=1,
        summary="Second checkpoint.", metadata={"created_at": "t2"},
    )
    store.index_checkpoint_summary(
        checkpoint_id="cp-b-1", conversation_id=conv_b, sequence_number=0,
        summary="Other conversation checkpoint.", metadata={"created_at": "t3"},
    )

    store.delete_conversation_checkpoints(conv_a)

    results_a = store.search_checkpoint_summaries(
        query="checkpoint", conversation_id=conv_a, limit=10,
    )
    assert results_a == []

    results_b = store.search_checkpoint_summaries(
        query="checkpoint", conversation_id=conv_b, limit=10,
    )
    assert len(results_b) == 1
    assert results_b[0].checkpoint_id == "cp-b-1"


def test_multiple_checkpoints_ranking(store: SummaryEmbeddingStore) -> None:
    conv = f"conv-{uuid.uuid4().hex[:8]}"

    target_summary = "Advanced Rust concurrency patterns and async runtime."
    store.index_checkpoint_summary(
        checkpoint_id="cp-1", conversation_id=conv, sequence_number=0,
        summary="Introduction to Rust programming language.",
        metadata={"created_at": "t1"},
    )
    store.index_checkpoint_summary(
        checkpoint_id="cp-2", conversation_id=conv, sequence_number=1,
        summary="Baking sourdough bread at home.",
        metadata={"created_at": "t2"},
    )
    store.index_checkpoint_summary(
        checkpoint_id="cp-3", conversation_id=conv, sequence_number=2,
        summary=target_summary,
        metadata={"created_at": "t3"},
    )

    results = store.search_checkpoint_summaries(
        query=target_summary,
        conversation_id=conv,
        limit=3,
    )
    assert len(results) == 3
    assert results[0].checkpoint_id == "cp-3"
    assert results[0].score > results[1].score
    assert results[0].score > results[2].score


def test_index_conversation_summary_stores_embedding(
    store: SummaryEmbeddingStore,
) -> None:
    conv_id = f"conv-{uuid.uuid4().hex[:8]}"
    summary = "The user discussed setting up a home server with Docker."
    metadata = {"created_at": "2025-01-01T18:00:00Z", "title": "Home Server"}

    store.index_conversation_summary(
        conversation_id=conv_id,
        summary=summary,
        metadata=metadata,
    )

    results = store.search_conversation_summaries(
        query="Docker home server", limit=5,
    )
    assert len(results) >= 1
    r = next(r for r in results if r.conversation_id == conv_id)
    assert isinstance(r, ConversationSearchResult)
    assert r.summary == summary
    assert r.score > 0.0
    assert r.metadata["title"] == "Home Server"
    assert r.metadata["created_at"] == "2025-01-01T18:00:00Z"


def test_search_conversation_summaries_excludes(
    store: SummaryEmbeddingStore,
) -> None:
    conv_a = f"conv-{uuid.uuid4().hex[:8]}"
    conv_b = f"conv-{uuid.uuid4().hex[:8]}"
    conv_c = f"conv-{uuid.uuid4().hex[:8]}"

    summary = "Discussion about Kubernetes cluster management."
    for cid in (conv_a, conv_b, conv_c):
        store.index_conversation_summary(
            conversation_id=cid,
            summary=summary,
            metadata={"created_at": "2025-01-01T12:00:00Z"},
        )

    results = store.search_conversation_summaries(
        query="Kubernetes", exclude_conversation_id=conv_b, limit=10,
    )
    conv_ids = {r.conversation_id for r in results}
    assert conv_b not in conv_ids
    assert conv_a in conv_ids
    assert conv_c in conv_ids


def test_delete_conversation_summary(store: SummaryEmbeddingStore) -> None:
    conv_id = f"conv-{uuid.uuid4().hex[:8]}"
    summary = "A conversation about neural network architectures."

    store.index_conversation_summary(
        conversation_id=conv_id,
        summary=summary,
        metadata={"created_at": "2025-01-01T12:00:00Z"},
    )

    results = store.search_conversation_summaries(
        query="neural network", limit=10,
    )
    assert any(r.conversation_id == conv_id for r in results)

    store.delete_conversation_summary(conv_id)
    results = store.search_conversation_summaries(
        query="neural network", limit=10,
    )
    assert all(r.conversation_id != conv_id for r in results)


def test_upsert_conversation_summary(store: SummaryEmbeddingStore) -> None:
    conv_id = f"conv-{uuid.uuid4().hex[:8]}"

    store.index_conversation_summary(
        conversation_id=conv_id,
        summary="Original summary about Python data analysis.",
        metadata={"created_at": "2025-01-01T09:00:00Z", "version": 1},
    )

    store.index_conversation_summary(
        conversation_id=conv_id,
        summary="Updated summary about Rust systems programming.",
        metadata={"created_at": "2025-01-01T10:00:00Z", "version": 2},
    )

    results = store.search_conversation_summaries(
        query="Rust systems programming", limit=10,
    )
    matching = [r for r in results if r.conversation_id == conv_id]
    assert len(matching) == 1
    assert matching[0].summary == "Updated summary about Rust systems programming."
    assert matching[0].metadata["version"] == 2

    results_old = store.search_conversation_summaries(
        query="Python data analysis", limit=10,
    )
    matching_old = [r for r in results_old if r.conversation_id == conv_id]
    assert len(matching_old) == 1
    assert matching_old[0].summary == "Updated summary about Rust systems programming."


def test_upsert_checkpoint_summary(store: SummaryEmbeddingStore) -> None:
    checkpoint_id = f"cp-{uuid.uuid4().hex[:8]}"
    conv_id = f"conv-{uuid.uuid4().hex[:8]}"

    store.index_checkpoint_summary(
        checkpoint_id=checkpoint_id,
        conversation_id=conv_id,
        sequence_number=0,
        summary="Original checkpoint about database design.",
        metadata={"created_at": "t1", "version": 1},
    )

    store.index_checkpoint_summary(
        checkpoint_id=checkpoint_id,
        conversation_id=conv_id,
        sequence_number=0,
        summary="Updated checkpoint about API design patterns.",
        metadata={"created_at": "t2", "version": 2},
    )

    results = store.search_checkpoint_summaries(
        query="API design patterns", conversation_id=conv_id, limit=10,
    )
    assert len(results) == 1
    assert results[0].summary == "Updated checkpoint about API design patterns."
    assert results[0].metadata["version"] == 2


def test_singleton_get_reset_set() -> None:
    from ganesh_backend.services.summary_embeddings import (
        get_summary_embedding_store,
        reset_summary_embedding_store,
        set_summary_embedding_store,
    )

    reset_summary_embedding_store()
    store1 = get_summary_embedding_store()
    store2 = get_summary_embedding_store()
    assert store1 is store2

    custom = SummaryEmbeddingStore(uri=":memory:", embedder=HashEmbedder(32))
    set_summary_embedding_store(custom)
    assert get_summary_embedding_store() is custom

    reset_summary_embedding_store()
    store3 = get_summary_embedding_store()
    assert store3 is not custom
    assert store3 is not store1
