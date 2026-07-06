"""Proactive pattern detection engine (Task 35).

Detects recurring user behaviors of the form "user does X before Y" and stores
them as FLUID, non-rigid suggestions via the existing :class:`MemoryService`.

Design constraints (Task 35 falsifiable spec):
  - A pattern is detected after **3+ occurrences** of behavior X preceding
    behavior Y. At 3 occurrences ``confidence > 0.7``.
  - Patterns are stored as memories with metadata ``{"type": "pattern"}`` so
    they coexist with regular memories and are scoped by ``profile_id``.
  - Patterns are **FLUID**: stored as soft suggestions, never auto-executed.
    The assistant may *offer* a suggestion but must not act without user
    confirmation.
  - User actions:
      * **accept**   → confidence +0.1 (capped at 1.0). Pattern grows stronger.
      * **decline**  → confidence -0.2 (floored at 0.0). Pattern weakens.
      * **disable**  → status set to ``"archived"``. Never suggested again.
  - Patterns NEVER auto-execute — they only produce a suggestion string that
    the LLM may surface (or not) based on conversation context.

Confidence model
----------------
``confidence = min(1.0, 0.25 * occurrences)`` — at 3 occurrences confidence is
0.75 (> 0.7), satisfying the falsifiable spec:

    occurrences=1 → 0.25  (below threshold, not suggested)
    occurrences=2 → 0.50  (below threshold, not suggested)
    occurrences=3 → 0.75  (above threshold, suggestion eligible)
    occurrences=4 → 1.00
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from ganesh_backend.services.memory import MemoryService, MemoryRecord


# Metadata key marking a memory as a pattern record.
PATTERN_TYPE = "pattern"

# Minimum number of occurrences before a pattern is eligible for suggestion.
DETECTION_THRESHOLD_OCCURRENCES = 3

# Confidence at/above which a pattern is eligible for suggestion.
SUGGESTION_CONFIDENCE_THRESHOLD = 0.7

# Confidence deltas applied on user actions.
ACCEPT_DELTA = 0.1
DECLINE_DELTA = -0.2

# Pattern statuses.
STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_confidence(occurrences: int) -> float:
    """Map occurrence count to a confidence in ``[0, 1]``.

    3 occurrences (the detection threshold) yields 0.75 > 0.7, satisfying the
    falsifiable spec ("3+ occurrences → confidence > 0.7"):

        occurrences=1 → 0.25  (below threshold, not suggested)
        occurrences=2 → 0.50  (below threshold, not suggested)
        occurrences=3 → 0.75  (above threshold, suggestion eligible)
        occurrences=4 → 1.00
    """
    if occurrences <= 0:
        return 0.0
    return min(1.0, 0.25 * occurrences)


@dataclass
class PatternRecord:
    """A detected behavioral pattern.

    Attributes
    ----------
    id:
        Unique identifier (also the underlying memory id).
    trigger:
        The preceding behavior X (e.g. "checks weather").
    followup:
        The subsequent behavior Y (e.g. "starts a meeting").
    occurrences:
        How many times X→Y has been observed.
    confidence:
        Fluid confidence in ``[0, 1]``.
    status:
        ``"active"`` or ``"archived"``. Archived patterns are never suggested.
    profile_id:
        Owning profile (may be ``None`` for unscoped tests).
    created_at / updated_at / last_suggested_at:
        ISO timestamps.
    """

    id: str
    trigger: str
    followup: str
    occurrences: int
    confidence: float
    status: str
    profile_id: Optional[str]
    created_at: str
    updated_at: str
    last_suggested_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "trigger": self.trigger,
            "followup": self.followup,
            "occurrences": self.occurrences,
            "confidence": self.confidence,
            "status": self.status,
            "profile_id": self.profile_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_suggested_at": self.last_suggested_at,
        }

    @classmethod
    def from_memory(cls, mem: MemoryRecord) -> "PatternRecord":
        meta = mem.metadata or {}
        return cls(
            id=mem.id,
            trigger=meta.get("trigger", ""),
            followup=meta.get("followup", ""),
            occurrences=int(meta.get("occurrences", 0)),
            confidence=float(meta.get("confidence", 0.0)),
            status=meta.get("status", STATUS_ACTIVE),
            profile_id=meta.get("profile_id"),
            created_at=mem.created_at,
            updated_at=mem.updated_at,
            last_suggested_at=meta.get("last_suggested_at"),
        )

    def to_metadata(self) -> dict[str, Any]:
        return {
            "type": PATTERN_TYPE,
            "trigger": self.trigger,
            "followup": self.followup,
            "occurrences": self.occurrences,
            "confidence": self.confidence,
            "status": self.status,
            "profile_id": self.profile_id,
            "last_suggested_at": self.last_suggested_at,
        }

    def to_content(self) -> str:
        return f"User often does {self.trigger} before {self.followup}."


class PatternService:
    """Detects, stores, and mutates behavioral patterns.

    Patterns are persisted as memories (metadata ``type: "pattern"``) via the
    injected :class:`MemoryService`. The service is otherwise stateless —
    every call re-reads from the memory store.
    """

    def __init__(self, memory_service: MemoryService) -> None:
        self._memory = memory_service

    # ---- detection --------------------------------------------------------

    def record_behavior(
        self,
        trigger: str,
        followup: str,
        profile_id: Optional[str] = None,
    ) -> PatternRecord:
        """Record one occurrence of ``trigger`` preceding ``followup``.

        If a matching active pattern already exists, its occurrence count is
        incremented and confidence recomputed. Otherwise a new pattern is
        created with ``occurrences=1``.
        """
        trigger = (trigger or "").strip()
        followup = (followup or "").strip()
        if not trigger or not followup:
            raise ValueError("trigger and followup must be non-empty")

        existing = self._find_pattern(trigger, followup, profile_id)
        if existing is None:
            now = _now_iso()
            pattern = PatternRecord(
                id="",
                trigger=trigger,
                followup=followup,
                occurrences=1,
                confidence=_compute_confidence(1),
                status=STATUS_ACTIVE,
                profile_id=profile_id,
                created_at=now,
                updated_at=now,
                last_suggested_at=None,
            )
            stored = self._memory.store_memory(
                content=pattern.to_content(),
                metadata=pattern.to_metadata(),
                profile_id=profile_id,
            )
            pattern.id = stored.id
            return pattern

        existing.occurrences += 1
        existing.confidence = _compute_confidence(existing.occurrences)
        existing.updated_at = _now_iso()
        self._memory.update_memory(
            existing.id,
            content=existing.to_content(),
            metadata=existing.to_metadata(),
            profile_id=profile_id,
        )
        return existing

    def get_pattern(
        self, pattern_id: str, profile_id: Optional[str] = None
    ) -> Optional[PatternRecord]:
        mem = self._memory.get_memory(pattern_id, profile_id=profile_id)
        if mem is None:
            return None
        meta = mem.metadata or {}
        if meta.get("type") != PATTERN_TYPE:
            return None
        return PatternRecord.from_memory(mem)

    def list_patterns(
        self,
        profile_id: Optional[str] = None,
        include_archived: bool = False,
    ) -> list[PatternRecord]:
        """List patterns for ``profile_id``. Excludes archived by default."""
        out: list[PatternRecord] = []
        for mem in self._memory.list_memories(profile_id=profile_id):
            meta = mem.metadata or {}
            if meta.get("type") != PATTERN_TYPE:
                continue
            if not include_archived and meta.get("status") == STATUS_ARCHIVED:
                continue
            out.append(PatternRecord.from_memory(mem))
        return out

    def get_suggestible_patterns(
        self, profile_id: Optional[str] = None
    ) -> list[PatternRecord]:
        """Return active patterns eligible for suggestion.

        A pattern is suggestible when:
          * status is ``active``
          * occurrences >= ``DETECTION_THRESHOLD_OCCURRENCES``
          * confidence >= ``SUGGESTION_CONFIDENCE_THRESHOLD``
        """
        out: list[PatternRecord] = []
        for p in self.list_patterns(profile_id=profile_id, include_archived=False):
            if (
                p.occurrences >= DETECTION_THRESHOLD_OCCURRENCES
                and p.confidence >= SUGGESTION_CONFIDENCE_THRESHOLD
            ):
                out.append(p)
        return out

    # ---- user actions -----------------------------------------------------

    def accept_pattern(
        self, pattern_id: str, profile_id: Optional[str] = None
    ) -> Optional[PatternRecord]:
        """Accept a suggestion: confidence +0.1 (capped at 1.0)."""
        p = self.get_pattern(pattern_id, profile_id=profile_id)
        if p is None or p.status != STATUS_ACTIVE:
            return None
        p.confidence = min(1.0, p.confidence + ACCEPT_DELTA)
        p.updated_at = _now_iso()
        self._memory.update_memory(
            p.id,
            content=p.to_content(),
            metadata=p.to_metadata(),
            profile_id=profile_id,
        )
        return p

    def decline_pattern(
        self, pattern_id: str, profile_id: Optional[str] = None
    ) -> Optional[PatternRecord]:
        """Decline a suggestion: confidence -0.2 (floored at 0.0)."""
        p = self.get_pattern(pattern_id, profile_id=profile_id)
        if p is None or p.status != STATUS_ACTIVE:
            return None
        p.confidence = max(0.0, p.confidence + DECLINE_DELTA)
        p.updated_at = _now_iso()
        self._memory.update_memory(
            p.id,
            content=p.to_content(),
            metadata=p.to_metadata(),
            profile_id=profile_id,
        )
        return p

    def disable_pattern(
        self, pattern_id: str, profile_id: Optional[str] = None
    ) -> Optional[PatternRecord]:
        """Disable a pattern: status → archived. Never suggested again."""
        p = self.get_pattern(pattern_id, profile_id=profile_id)
        if p is None:
            return None
        p.status = STATUS_ARCHIVED
        p.updated_at = _now_iso()
        self._memory.update_memory(
            p.id,
            content=p.to_content(),
            metadata=p.to_metadata(),
            profile_id=profile_id,
        )
        return p

    def mark_suggested(
        self, pattern_id: str, profile_id: Optional[str] = None
    ) -> None:
        """Record that a pattern was surfaced as a suggestion."""
        p = self.get_pattern(pattern_id, profile_id=profile_id)
        if p is None:
            return
        p.last_suggested_at = _now_iso()
        p.updated_at = p.last_suggested_at
        self._memory.update_memory(
            p.id,
            content=p.to_content(),
            metadata=p.to_metadata(),
            profile_id=profile_id,
        )

    # ---- internals --------------------------------------------------------

    def _find_pattern(
        self,
        trigger: str,
        followup: str,
        profile_id: Optional[str],
    ) -> Optional[PatternRecord]:
        for p in self.list_patterns(
            profile_id=profile_id, include_archived=True
        ):
            if p.trigger == trigger and p.followup == followup:
                return p
        return None


# ---------------------------------------------------------------------------
# Process-wide singleton (mirrors memory / emotion / personality pattern).
# ---------------------------------------------------------------------------

_service: Optional[PatternService] = None


def get_pattern_service() -> PatternService:
    global _service
    if _service is None:
        from ganesh_backend.routers.memory import get_memory_service

        _service = PatternService(memory_service=get_memory_service())
    return _service


def set_pattern_service(svc: PatternService) -> None:
    global _service
    _service = svc


def reset_pattern_service() -> None:
    global _service
    _service = None


__all__ = [
    "ACCEPT_DELTA",
    "DECLINE_DELTA",
    "DETECTION_THRESHOLD_OCCURRENCES",
    "PATTERN_TYPE",
    "STATUS_ACTIVE",
    "STATUS_ARCHIVED",
    "SUGGESTION_CONFIDENCE_THRESHOLD",
    "PatternRecord",
    "PatternService",
    "get_pattern_service",
    "reset_pattern_service",
    "set_pattern_service",
]
