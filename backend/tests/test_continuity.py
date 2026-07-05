"""Tests for session continuity memory + temporal awareness (Task 33).

Covers:
  - test_welcome_back_message: message contains temporal phrase + last topic
  - test_epoch_delta: correct time delta via epoch seconds
  - test_first_run_no_welcome: no message on first launch
  - test_no_welcome_within_threshold: gap <= 5 minutes returns None
  - test_start_end_session: session lifecycle + retrieval
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from ganesh_backend.services.continuity import (  # noqa: E402
    ContinuityService,
    _format_duration,
)


@pytest.fixture
def svc(tmp_path: Path) -> ContinuityService:
    return ContinuityService(db_path=str(tmp_path / "continuity.db"))


# ---------------------------------------------------------------------------
# Test 1: welcome-back message contains temporal phrase + last topic
# ---------------------------------------------------------------------------


def test_welcome_back_message(svc: ContinuityService) -> None:
    profile_id = "profile-1"
    session = svc.start_session(profile_id)
    svc.end_session(session.id, last_topic="quarterly report", last_task_id="t-42")

    # Backdate ended_at so the gap exceeds the threshold (injectable `now`).
    past_ended = time.time() - 7200  # 2 hours ago
    with svc._lock:  # noqa: SLF001
        svc._conn.execute(  # noqa: SLF001
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (past_ended, session.id),
        )
        svc._conn.commit()

    payload = svc.generate_welcome_back(profile_id)
    assert payload is not None
    msg = payload["message"]
    assert "Welcome back!" in msg
    assert "quarterly report" in msg
    assert "Want to continue?" in msg
    assert "It's been" in msg
    assert payload["last_topic"] == "quarterly report"
    assert payload["last_task_id"] == "t-42"
    assert payload["last_session_id"] == session.id
    assert payload["duration_seconds"] >= 7200
    assert "hour" in payload["duration_phrase"]


# ---------------------------------------------------------------------------
# Test 2: correct time delta via epoch seconds
# ---------------------------------------------------------------------------


def test_epoch_delta(svc: ContinuityService) -> None:
    profile_id = "profile-2"
    session = svc.start_session(profile_id)
    started_at = session.started_at
    # epoch seconds are ~1.7 billion in 2026; monotonic would be tiny.
    assert started_at > 1_000_000_000

    svc.end_session(session.id, last_topic="x")
    past_ended = time.time() - 900  # 15 minutes ago
    with svc._lock:  # noqa: SLF001
        svc._conn.execute(  # noqa: SLF001
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (past_ended, session.id),
        )
        svc._conn.commit()

    last = svc.get_last_session(profile_id)
    assert last is not None
    assert last.ended_at is not None
    # Delta computed from epoch seconds should be ~900s.
    delta = time.time() - last.ended_at
    assert 890 <= delta <= 920

    # Use the injectable `now` to make the assertion deterministic.
    now = time.time()
    payload = svc.generate_welcome_back(profile_id, now=now)
    assert payload is not None
    assert payload["duration_seconds"] == pytest.approx(now - past_ended, abs=2)
    assert "15 minute" in payload["duration_phrase"]


# ---------------------------------------------------------------------------
# Test 3: first run -> no welcome
# ---------------------------------------------------------------------------


def test_first_run_no_welcome(svc: ContinuityService) -> None:
    assert svc.generate_welcome_back("never-seen-profile") is None


# ---------------------------------------------------------------------------
# Test 4: gap <= threshold -> no welcome
# ---------------------------------------------------------------------------


def test_no_welcome_within_threshold(svc: ContinuityService) -> None:
    profile_id = "profile-3"
    session = svc.start_session(profile_id)
    svc.end_session(session.id, last_topic="fresh work")
    # Just ended -> gap is ~0s, well under the 5-minute threshold.
    assert svc.generate_welcome_back(profile_id) is None

    # Even at exactly the threshold, no welcome (<=).
    last = svc.get_last_session(profile_id)
    assert last is not None and last.ended_at is not None
    now = last.ended_at + svc._threshold  # noqa: SLF001
    assert svc.generate_welcome_back(profile_id, now=now) is None

    # One second past the threshold -> welcome.
    now = last.ended_at + svc._threshold + 1  # noqa: SLF001
    payload = svc.generate_welcome_back(profile_id, now=now)
    assert payload is not None


# ---------------------------------------------------------------------------
# Test 5: session lifecycle
# ---------------------------------------------------------------------------


def test_start_end_session(svc: ContinuityService) -> None:
    profile_id = "profile-4"
    s = svc.start_session(profile_id)
    assert s.profile_id == profile_id
    assert s.ended_at is None
    assert s.last_topic is None

    ended = svc.end_session(s.id, last_topic="topic", last_task_id="task-1")
    assert ended is not None
    assert ended.ended_at is not None
    assert ended.last_topic == "topic"
    assert ended.last_task_id == "task-1"

    last = svc.get_last_session(profile_id)
    assert last is not None
    assert last.id == s.id

    assert svc.get_open_session(profile_id) is None

    s2 = svc.start_session(profile_id)
    open_sess = svc.get_open_session(profile_id)
    assert open_sess is not None
    assert open_sess.id == s2.id


# ---------------------------------------------------------------------------
# Test 6: duration formatter
# ---------------------------------------------------------------------------


def test_format_duration_units() -> None:
    assert "second" in _format_duration(30)
    assert "minute" in _format_duration(120)
    assert "hour" in _format_duration(7200)
    assert "day" in _format_duration(172800)
