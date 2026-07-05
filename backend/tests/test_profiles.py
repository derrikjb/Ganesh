"""Tests for multi-user profiles + shared bridge memory layer (Task 31).

Covers:
  - test_create_profile: profile CRUD + active-profile tracking
  - test_profile_isolation: A's memories are not visible to B
  - test_bridge_grant: A grants → B can query A's memory
  - test_bridge_revoke: revocation immediately blocks access
  - test_profile_deletion_cascade: deleting a profile removes its memories + grants
  - test_bridge_audit_log: every bridge query is logged
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
from ganesh_backend.services.bridge import BridgeService
from ganesh_backend.services.memory import MemoryService
from ganesh_backend.services.profiles import ProfileManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def profile_mgr(tmp_path: Path) -> ProfileManager:
    return ProfileManager(db_path=str(tmp_path / "profiles.db"))


@pytest.fixture
def memory_service(tmp_path: Path) -> MemoryService:
    return MemoryService(
        db_path=str(tmp_path / "lancedb"),
        embedder=HashEmbedder(dimension=64),
        collection_name=f"test_memories_{uuid.uuid4().hex[:8]}",
    )


@pytest.fixture
def bridge_service(
    tmp_path: Path, memory_service: MemoryService
) -> BridgeService:
    return BridgeService(
        db_path=str(tmp_path / "bridge.db"),
        memory_service=memory_service,
    )


# ---------------------------------------------------------------------------
# Test 1: create profile + active-profile tracking
# ---------------------------------------------------------------------------


def test_create_profile(profile_mgr: ProfileManager) -> None:
    # First profile is auto-activated.
    a = profile_mgr.create_profile(name="Work", description="Work profile", color="#ff0000")
    assert a.id
    assert a.name == "Work"
    assert a.description == "Work profile"
    assert a.color == "#ff0000"
    assert profile_mgr.get_active_profile_id() == a.id

    # Second profile does NOT auto-activate.
    b = profile_mgr.create_profile(name="Personal", color="#00ff00")
    assert b.id != a.id
    assert profile_mgr.get_active_profile_id() == a.id

    # Explicit activation.
    profile_mgr.activate_profile(b.id)
    assert profile_mgr.get_active_profile_id() == b.id
    assert profile_mgr.get_active_profile().id == b.id

    # List returns both, ordered by creation time.
    profiles = profile_mgr.list_profiles()
    assert [p.name for p in profiles] == ["Work", "Personal"]

    # Update.
    updated = profile_mgr.update_profile(a.id, name="Work V2", description="Updated")
    assert updated.name == "Work V2"
    assert updated.description == "Updated"

    # Cannot delete the last profile.
    profile_mgr.delete_profile(b.id)
    with pytest.raises(ValueError):
        profile_mgr.delete_profile(a.id)


# ---------------------------------------------------------------------------
# Test 2: profile isolation — A's memories are not visible to B
# ---------------------------------------------------------------------------


def test_profile_isolation(
    profile_mgr: ProfileManager, memory_service: MemoryService
) -> None:
    a = profile_mgr.create_profile(name="A")
    b = profile_mgr.create_profile(name="B")

    memory_service.store_memory(
        content="Team meeting on Friday at 2pm", profile_id=a.id
    )
    memory_service.store_memory(
        content="Grocery list: milk, eggs, bread", profile_id=b.id
    )

    a_mems = memory_service.list_memories(profile_id=a.id)
    b_mems = memory_service.list_memories(profile_id=b.id)
    assert len(a_mems) == 1
    assert len(b_mems) == 1
    assert "Friday" in a_mems[0].content
    assert "milk" in b_mems[0].content

    # Semantic search scoped to A does not return B's memory.
    a_results = memory_service.retrieve_memories(
        query="grocery", profile_id=a.id, limit=5
    )
    assert all("milk" not in r.content for r in a_results)
    b_results = memory_service.retrieve_memories(
        query="meeting", profile_id=b.id, limit=5
    )
    assert all("Friday" not in r.content for r in b_results)


# ---------------------------------------------------------------------------
# Test 3: bridge grant — A grants → B can query A's memory
# ---------------------------------------------------------------------------


def test_bridge_grant(
    profile_mgr: ProfileManager,
    memory_service: MemoryService,
    bridge_service: BridgeService,
) -> None:
    a = profile_mgr.create_profile(name="A")
    b = profile_mgr.create_profile(name="B")

    record = memory_service.store_memory(
        content="Team meeting on Friday at 2pm", profile_id=a.id
    )

    # Without a grant, B's query returns nothing.
    no_results = bridge_service.query(
        receiving_profile_id=b.id,
        granting_profile_id=a.id,
        query="meeting schedule",
    )
    assert no_results == []

    # Grant access.
    grant = bridge_service.grant(
        granting_profile_id=a.id,
        receiving_profile_id=b.id,
        memory_id=record.id,
    )
    assert grant.id
    assert grant.granting_profile_id == a.id
    assert grant.receiving_profile_id == b.id
    assert grant.memory_id == record.id

    # Now B can query and find the meeting memory.
    results = bridge_service.query(
        receiving_profile_id=b.id,
        granting_profile_id=a.id,
        query="meeting schedule",
    )
    assert len(results) >= 1
    assert any("Friday" in r.content for r in results)


# ---------------------------------------------------------------------------
# Test 4: bridge revoke — revocation immediately blocks access
# ---------------------------------------------------------------------------


def test_bridge_revoke(
    profile_mgr: ProfileManager,
    memory_service: MemoryService,
    bridge_service: BridgeService,
) -> None:
    a = profile_mgr.create_profile(name="A")
    b = profile_mgr.create_profile(name="B")

    record = memory_service.store_memory(
        content="Secret project roadmap Q4", profile_id=a.id
    )
    grant = bridge_service.grant(
        granting_profile_id=a.id,
        receiving_profile_id=b.id,
        memory_id=record.id,
    )

    # Access works before revocation.
    results = bridge_service.query(
        receiving_profile_id=b.id,
        granting_profile_id=a.id,
        query="project roadmap",
    )
    assert len(results) >= 1

    # Revoke.
    assert bridge_service.revoke(grant.id) is True
    assert bridge_service.revoke(grant.id) is False  # already revoked

    # Access is now blocked.
    blocked = bridge_service.query(
        receiving_profile_id=b.id,
        granting_profile_id=a.id,
        query="project roadmap",
    )
    assert blocked == []


# ---------------------------------------------------------------------------
# Test 5: profile deletion cascade — memories + grants deleted
# ---------------------------------------------------------------------------


def test_profile_deletion_cascade(
    profile_mgr: ProfileManager,
    memory_service: MemoryService,
    bridge_service: BridgeService,
) -> None:
    a = profile_mgr.create_profile(name="A")
    b = profile_mgr.create_profile(name="B")

    a_record = memory_service.store_memory(
        content="A's private memory", profile_id=a.id
    )
    b_record = memory_service.store_memory(
        content="B's private memory", profile_id=b.id
    )
    grant = bridge_service.grant(
        granting_profile_id=a.id,
        receiving_profile_id=b.id,
        memory_id=a_record.id,
    )

    # Cascade: delete A's memories + grants, then the profile row.
    removed = memory_service.delete_memories_for_profile(a.id)
    assert removed == 1
    bridge_service.revoke_grants_for_profile(a.id)
    assert bridge_service.get_grant(grant.id) is None

    # A's memory is gone; B's memory is unaffected.
    assert memory_service.list_memories(profile_id=a.id) == []
    b_mems = memory_service.list_memories(profile_id=b.id)
    assert len(b_mems) == 1
    assert b_mems[0].id == b_record.id

    # Now delete profile A (B remains so the "last profile" guard passes).
    assert profile_mgr.delete_profile(a.id) is True
    assert profile_mgr.get_profile(a.id) is None
    assert profile_mgr.get_profile(b.id) is not None


# ---------------------------------------------------------------------------
# Test 6: bridge audit log — every query is logged
# ---------------------------------------------------------------------------


def test_bridge_audit_log(
    profile_mgr: ProfileManager,
    memory_service: MemoryService,
    bridge_service: BridgeService,
) -> None:
    a = profile_mgr.create_profile(name="A")
    b = profile_mgr.create_profile(name="B")

    record = memory_service.store_memory(
        content="Quarterly earnings report", profile_id=a.id
    )
    bridge_service.grant(
        granting_profile_id=a.id,
        receiving_profile_id=b.id,
        memory_id=record.id,
    )

    # Query twice.
    bridge_service.query(
        receiving_profile_id=b.id,
        granting_profile_id=a.id,
        query="earnings",
    )
    bridge_service.query(
        receiving_profile_id=b.id,
        granting_profile_id=a.id,
        query="financial report",
    )

    # A query with no grants also logs.
    bridge_service.query(
        receiving_profile_id=a.id,
        granting_profile_id=b.id,
        query="nothing here",
    )

    entries = bridge_service.list_audit()
    assert len(entries) == 3
    # Ordered DESC by id (most recent first).
    assert entries[0].query == "nothing here"
    assert entries[0].receiving_profile_id == a.id
    assert entries[0].granting_profile_id == b.id
    assert entries[1].query == "financial report"
    assert entries[1].receiving_profile_id == b.id
    assert entries[1].granting_profile_id == a.id
    assert entries[2].query == "earnings"
    assert all(e.timestamp for e in entries)

    # Filter by receiving_profile.
    b_entries = bridge_service.list_audit(receiving_profile_id=b.id)
    assert len(b_entries) == 2
    assert all(e.receiving_profile_id == b.id for e in b_entries)
