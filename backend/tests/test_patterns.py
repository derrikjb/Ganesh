"""Tests for proactive pattern suggestions (Task 35).

Covers the four required falsifiable tests:
  - test_pattern_detection       — 3 occurrences → confidence > 0.7
  - test_pattern_fluidity        — suggestion is offered, not forced
  - test_pattern_decline          — confidence decreases by 0.2
  - test_pattern_disable          — archived, not suggested again

Plus additional coverage for accept, singleton, router integration.
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
from ganesh_backend.services.memory import MemoryService  # noqa: E402
from ganesh_backend.services.patterns import (  # noqa: E402
    ACCEPT_DELTA,
    DECLINE_DELTA,
    DETECTION_THRESHOLD_OCCURRENCES,
    PATTERN_TYPE,
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    SUGGESTION_CONFIDENCE_THRESHOLD,
    PatternService,
    get_pattern_service,
    reset_pattern_service,
    set_pattern_service,
)
from ganesh_backend.services.suggestion_engine import (  # noqa: E402
    SuggestionEngine,
    get_suggestion_engine,
    reset_suggestion_engine,
    set_suggestion_engine,
)


@pytest.fixture
def memory_service() -> MemoryService:
    return MemoryService(
        db_path=":memory:",
        embedder=HashEmbedder(dimension=64),
        collection_name=f"test_patterns_{uuid.uuid4().hex[:8]}",
    )


@pytest.fixture
def service(memory_service: MemoryService) -> PatternService:
    return PatternService(memory_service=memory_service)


@pytest.fixture(autouse=True)
def _reset_singletons() -> None:
    reset_pattern_service()
    reset_suggestion_engine()
    yield
    reset_pattern_service()
    reset_suggestion_engine()


# ---------------------------------------------------------------------------
# test_pattern_detection — 3 occurrences → confidence > 0.7
# ---------------------------------------------------------------------------


def test_pattern_detection(service: PatternService) -> None:
    p = None
    for _ in range(DETECTION_THRESHOLD_OCCURRENCES):
        p = service.record_behavior(
            trigger="checks weather", followup="starts meeting"
        )
    assert p is not None
    assert p.occurrences == DETECTION_THRESHOLD_OCCURRENCES
    assert p.confidence > 0.7, (
        f"expected confidence > 0.7 after 3 occurrences, got {p.confidence}"
    )
    assert p.status == STATUS_ACTIVE

    suggestible = service.get_suggestible_patterns()
    assert any(s.id == p.id for s in suggestible)


def test_pattern_below_threshold_not_suggested(service: PatternService) -> None:
    p = service.record_behavior(
        trigger="checks weather", followup="starts meeting"
    )
    assert p.occurrences == 1
    assert p.confidence < SUGGESTION_CONFIDENCE_THRESHOLD
    assert service.get_suggestible_patterns() == []


# ---------------------------------------------------------------------------
# test_pattern_fluidity — suggestion is offered, not forced
# ---------------------------------------------------------------------------


def test_pattern_fluidity(service: PatternService) -> None:
    for _ in range(DETECTION_THRESHOLD_OCCURRENCES):
        service.record_behavior(
            trigger="checks weather", followup="starts meeting"
        )

    engine = SuggestionEngine(pattern_service=service)
    suggestion = engine.generate_suggestion(context="I will checks weather now")

    assert suggestion is not None
    assert "checks weather" in suggestion.note
    assert "starts meeting" in suggestion.note
    assert "fluid" in suggestion.note.lower()
    assert "never auto-execute" in suggestion.note.lower()

    assert "PATTERN SUGGESTION" in engine.build_system_note([suggestion])
    assert engine.build_system_note([]) == ""


def test_suggestion_returns_none_when_no_match(service: PatternService) -> None:
    for _ in range(DETECTION_THRESHOLD_OCCURRENCES):
        service.record_behavior(
            trigger="checks weather", followup="starts meeting"
        )
    engine = SuggestionEngine(pattern_service=service)
    assert engine.generate_suggestion(context="unrelated context") is None


def test_suggestion_returns_none_when_below_threshold(
    service: PatternService,
) -> None:
    service.record_behavior(trigger="checks weather", followup="starts meeting")
    engine = SuggestionEngine(pattern_service=service)
    assert engine.generate_suggestion(context="checks weather") is None


def test_suggestion_does_not_execute_action(service: PatternService) -> None:
    """The suggestion engine must only return a string — never mutate state
    beyond marking the pattern as suggested."""
    for _ in range(DETECTION_THRESHOLD_OCCURRENCES):
        service.record_behavior(trigger="X", followup="Y")
    engine = SuggestionEngine(pattern_service=service)
    suggestion = engine.generate_suggestion(context="X")
    assert suggestion is not None
    assert isinstance(suggestion.note, str)
    assert isinstance(suggestion.pattern_id, str)


# ---------------------------------------------------------------------------
# test_pattern_decline — confidence decreases by 0.2
# ---------------------------------------------------------------------------


def test_pattern_decline(service: PatternService) -> None:
    for _ in range(DETECTION_THRESHOLD_OCCURRENCES):
        p = service.record_behavior(trigger="X", followup="Y")
    original_confidence = p.confidence

    declined = service.decline_pattern(p.id)
    assert declined is not None
    assert abs((declined.confidence - original_confidence) - DECLINE_DELTA) < 1e-9


def test_pattern_decline_floored_at_zero(service: PatternService) -> None:
    p = service.record_behavior(trigger="X", followup="Y")
    original = p.confidence

    declined = service.decline_pattern(p.id)
    assert declined is not None
    assert abs((declined.confidence - original) - DECLINE_DELTA) < 1e-9

    for _ in range(10):
        declined = service.decline_pattern(p.id)
    assert declined is not None
    assert declined.confidence == 0.0


def test_pattern_decline_makes_pattern_unsuggestible(
    service: PatternService,
) -> None:
    for _ in range(DETECTION_THRESHOLD_OCCURRENCES):
        p = service.record_behavior(trigger="X", followup="Y")
    assert service.get_suggestible_patterns()

    for _ in range(10):
        service.decline_pattern(p.id)

    assert all(s.id != p.id for s in service.get_suggestible_patterns())


# ---------------------------------------------------------------------------
# test_pattern_disable — archived, not suggested again
# ---------------------------------------------------------------------------


def test_pattern_disable(service: PatternService) -> None:
    for _ in range(DETECTION_THRESHOLD_OCCURRENCES):
        p = service.record_behavior(trigger="X", followup="Y")
    assert any(s.id == p.id for s in service.get_suggestible_patterns())

    disabled = service.disable_pattern(p.id)
    assert disabled is not None
    assert disabled.status == STATUS_ARCHIVED

    assert all(s.id != p.id for s in service.get_suggestible_patterns())

    engine = SuggestionEngine(pattern_service=service)
    assert engine.generate_suggestion(context="X") is None


def test_disabled_pattern_not_listed_by_default(service: PatternService) -> None:
    p = service.record_behavior(trigger="X", followup="Y")
    service.disable_pattern(p.id)
    active = service.list_patterns()
    assert all(pat.id != p.id for pat in active)
    archived = service.list_patterns(include_archived=True)
    assert any(pat.id == p.id and pat.status == STATUS_ARCHIVED for pat in archived)


def test_disable_idempotent(service: PatternService) -> None:
    p = service.record_behavior(trigger="X", followup="Y")
    first = service.disable_pattern(p.id)
    second = service.disable_pattern(p.id)
    assert first is not None
    assert second is not None
    assert second.status == STATUS_ARCHIVED


# ---------------------------------------------------------------------------
# test_pattern_accept — confidence increases by 0.1
# ---------------------------------------------------------------------------


def test_pattern_accept(service: PatternService) -> None:
    for _ in range(DETECTION_THRESHOLD_OCCURRENCES):
        p = service.record_behavior(trigger="X", followup="Y")
    original = p.confidence

    accepted = service.accept_pattern(p.id)
    assert accepted is not None
    assert abs((accepted.confidence - original) - ACCEPT_DELTA) < 1e-9


def test_pattern_accept_capped_at_one(service: PatternService) -> None:
    for _ in range(DETECTION_THRESHOLD_OCCURRENCES):
        p = service.record_behavior(trigger="X", followup="Y")
    for _ in range(20):
        accepted = service.accept_pattern(p.id)
    assert accepted is not None
    assert accepted.confidence == 1.0


# ---------------------------------------------------------------------------
# Persistence via MemoryService — patterns stored as type:"pattern"
# ---------------------------------------------------------------------------


def test_pattern_stored_as_pattern_memory(
    service: PatternService, memory_service: MemoryService
) -> None:
    service.record_behavior(trigger="X", followup="Y")
    memories = memory_service.list_memories()
    assert any(m.metadata.get("type") == PATTERN_TYPE for m in memories)


def test_pattern_increments_existing(service: PatternService) -> None:
    p1 = service.record_behavior(trigger="X", followup="Y")
    p2 = service.record_behavior(trigger="X", followup="Y")
    assert p1.id == p2.id
    assert p2.occurrences == 2


def test_pattern_distinct_triggers(service: PatternService) -> None:
    a = service.record_behavior(trigger="A", followup="Y")
    b = service.record_behavior(trigger="B", followup="Y")
    assert a.id != b.id


def test_record_behavior_rejects_empty(service: PatternService) -> None:
    with pytest.raises(ValueError):
        service.record_behavior(trigger="", followup="Y")
    with pytest.raises(ValueError):
        service.record_behavior(trigger="X", followup="")


# ---------------------------------------------------------------------------
# Singleton lifecycle
# ---------------------------------------------------------------------------


def test_singleton_get_set_reset(
    memory_service: MemoryService,
) -> None:
    custom = PatternService(memory_service=memory_service)
    set_pattern_service(custom)
    assert get_pattern_service() is custom
    reset_pattern_service()
    assert get_pattern_service() is not custom


def test_suggestion_engine_singleton() -> None:
    e1 = get_suggestion_engine()
    e2 = get_suggestion_engine()
    assert e1 is e2
    custom = SuggestionEngine()
    set_suggestion_engine(custom)
    assert get_suggestion_engine() is custom
    reset_suggestion_engine()
    assert get_suggestion_engine() is not custom


# ---------------------------------------------------------------------------
# Router integration (FastAPI TestClient)
# ---------------------------------------------------------------------------


def test_patterns_router_endpoints(
    memory_service: MemoryService,
) -> None:
    from fastapi.testclient import TestClient

    from main import create_app

    custom = PatternService(memory_service=memory_service)
    set_pattern_service(custom)
    set_suggestion_engine(SuggestionEngine(pattern_service=custom))

    app = create_app()
    client = TestClient(app)

    for _ in range(DETECTION_THRESHOLD_OCCURRENCES):
        resp = client.post(
            "/api/patterns/record",
            json={"trigger": "checks weather", "followup": "starts meeting"},
        )
        assert resp.status_code == 201
    body = resp.json()
    assert body["occurrences"] == DETECTION_THRESHOLD_OCCURRENCES
    assert body["confidence"] > 0.7
    pattern_id = body["id"]

    listed = client.get("/api/patterns")
    assert listed.status_code == 200
    assert any(p["id"] == pattern_id for p in listed.json()["patterns"])

    suggestible = client.get("/api/patterns/suggestible")
    assert suggestible.status_code == 200
    assert any(p["id"] == pattern_id for p in suggestible.json()["patterns"])

    suggest_resp = client.post(
        "/api/patterns/suggest",
        json={"context": "I will checks weather now", "limit": 3},
    )
    assert suggest_resp.status_code == 200
    sbody = suggest_resp.json()
    assert sbody["suggestion"] is not None
    assert "checks weather" in sbody["note"]

    accept_resp = client.post(f"/api/patterns/{pattern_id}/accept")
    assert accept_resp.status_code == 200
    assert accept_resp.json()["confidence"] > body["confidence"]

    decline_resp = client.post(f"/api/patterns/{pattern_id}/decline")
    assert decline_resp.status_code == 200
    declined = decline_resp.json()
    assert declined["confidence"] < accept_resp.json()["confidence"]

    disable_resp = client.post(f"/api/patterns/{pattern_id}/disable")
    assert disable_resp.status_code == 200
    assert disable_resp.json()["status"] == STATUS_ARCHIVED

    suggestible2 = client.get("/api/patterns/suggestible")
    assert all(
        p["id"] != pattern_id for p in suggestible2.json()["patterns"]
    )

    reset_pattern_service()
    reset_suggestion_engine()


def test_patterns_router_404(memory_service: MemoryService) -> None:
    from fastapi.testclient import TestClient

    from main import create_app

    set_pattern_service(PatternService(memory_service=memory_service))
    set_suggestion_engine(SuggestionEngine())

    app = create_app()
    client = TestClient(app)

    resp = client.post("/api/patterns/nonexistent/accept")
    assert resp.status_code == 404

    reset_pattern_service()
    reset_suggestion_engine()
