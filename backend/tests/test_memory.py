"""Tests for the memory service (LanceDB + local embeddings).

Uses in-memory LanceDB (URI ``":memory:"``) and a deterministic
``HashEmbedder`` so no external services or model downloads are required.
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

from ganesh_backend.embeddings import HashEmbedder
from ganesh_backend.services.memory import MemoryService


@pytest.fixture
def service() -> MemoryService:
    return MemoryService(
        db_path=":memory:",
        embedder=HashEmbedder(dimension=64),
        collection_name=f"test_memories_{uuid.uuid4().hex[:8]}",
    )


def test_store_memory(service: MemoryService) -> None:
    record = service.store_memory(
        content="The user prefers dark mode for all applications.",
        metadata={"category": "preference"},
    )
    assert record.id
    assert record.content == "The user prefers dark mode for all applications."
    assert record.metadata == {"category": "preference"}
    assert record.created_at
    assert record.updated_at

    retrieved = service.retrieve_memories(query="dark mode preference", limit=5)
    assert len(retrieved) >= 1
    match = next((r for r in retrieved if r.id == record.id), None)
    assert match is not None
    assert "dark mode" in match.content.lower()


def test_retrieve_memories(service: MemoryService) -> None:
    service.store_memory(content="User likes Python programming language.")
    service.store_memory(content="The weather is sunny today.")
    service.store_memory(content="User enjoys hiking in the mountains.")

    results = service.retrieve_memories(query="programming language preference", limit=2)
    assert len(results) <= 2
    top = results[0]
    assert "python" in top.content.lower()


def test_update_memory(service: MemoryService) -> None:
    record = service.store_memory(content="Original content here.")
    updated = service.update_memory(record.id, content="Updated content here.")
    assert updated is not None
    assert updated.id == record.id
    assert updated.content == "Updated content here."
    assert updated.updated_at >= record.updated_at

    results = service.retrieve_memories(query="updated content", limit=5)
    match = next((r for r in results if r.id == record.id), None)
    assert match is not None
    assert match.content == "Updated content here."


def test_delete_memory(service: MemoryService) -> None:
    record = service.store_memory(content="This memory will be deleted.")
    assert service.delete_memory(record.id) is True
    assert service.delete_memory(record.id) is False
    all_memories = service.list_memories()
    assert all(r.id != record.id for r in all_memories)
