"""Proactive suggestion generator (Task 35).

On relevant context, checks for matching patterns and produces a **system
note** string that the LLM may surface (or not) based on conversation
context. Suggestions are FLUID — never auto-executed, never forced.

The generated note is injected as a ``system``-role message in the LLM
context. The LLM decides whether to surface it based on the conversation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ganesh_backend.services.patterns import (
    PatternRecord,
    PatternService,
    get_pattern_service,
)


@dataclass
class Suggestion:
    """A fluid suggestion produced from a matching pattern.

    ``note`` is the string to inject as a system note in the LLM context.
    ``pattern_id`` identifies the source pattern (for accept/decline/disable).
    """

    pattern_id: str
    trigger: str
    followup: str
    confidence: float
    note: str

    def to_dict(self) -> dict[str, object]:
        return {
            "pattern_id": self.pattern_id,
            "trigger": self.trigger,
            "followup": self.followup,
            "confidence": self.confidence,
            "note": self.note,
        }


class SuggestionEngine:
    """Generates fluid suggestions from matching patterns.

    The engine is stateless beyond the injected :class:`PatternService`.
    It never executes any action — it only returns a suggestion note that
    the caller (router / chat flow) may inject into the LLM context.
    """

    def __init__(self, pattern_service: Optional[PatternService] = None) -> None:
        self._patterns = pattern_service

    def _service(self) -> PatternService:
        return self._patterns if self._patterns is not None else get_pattern_service()

    def generate_suggestion(
        self,
        context: str,
        profile_id: Optional[str] = None,
    ) -> Optional[Suggestion]:
        """Return a suggestion note for the first matching pattern, or ``None``.

        Matching is intentionally simple: a pattern matches when the context
        mentions the pattern's trigger behavior. The LLM ultimately decides
        whether to surface the suggestion — this is the FLUID contract.
        """
        if not context or not context.strip():
            return None
        ctx_lower = context.lower()
        service = self._service()
        for pattern in service.get_suggestible_patterns(profile_id=profile_id):
            if pattern.trigger.lower() in ctx_lower:
                note = self._build_note(pattern)
                service.mark_suggested(pattern.id, profile_id=profile_id)
                return Suggestion(
                    pattern_id=pattern.id,
                    trigger=pattern.trigger,
                    followup=pattern.followup,
                    confidence=pattern.confidence,
                    note=note,
                )
        return None

    def generate_suggestions(
        self,
        context: str,
        profile_id: Optional[str] = None,
        limit: int = 3,
    ) -> list[Suggestion]:
        """Return up to ``limit`` matching suggestions. Fluid — never forced."""
        if not context or not context.strip():
            return []
        ctx_lower = context.lower()
        service = self._service()
        out: list[Suggestion] = []
        for pattern in service.get_suggestible_patterns(profile_id=profile_id):
            if pattern.trigger.lower() in ctx_lower:
                out.append(
                    Suggestion(
                        pattern_id=pattern.id,
                        trigger=pattern.trigger,
                        followup=pattern.followup,
                        confidence=pattern.confidence,
                        note=self._build_note(pattern),
                    )
                )
                if len(out) >= limit:
                    break
        for s in out:
            service.mark_suggested(s.pattern_id, profile_id=profile_id)
        return out

    def build_system_note(self, suggestions: list[Suggestion]) -> str:
        """Compose a single system-note string from multiple suggestions.

        Returns an empty string when there are no suggestions, so callers
        can treat the return as a falsy "no suggestion" signal.
        """
        if not suggestions:
            return ""
        lines = ["[PATTERN SUGGESTION]"]
        for s in suggestions:
            lines.append(
                f"- User often does {s.trigger} before {s.followup}. "
                f"Consider offering to help with {s.followup}. "
                f"(confidence={s.confidence:.2f}; fluid — surface only if "
                f"contextually relevant; never auto-execute.)"
            )
        return "\n".join(lines)

    @staticmethod
    def _build_note(p: PatternRecord) -> str:
        return (
            f"User often does {p.trigger} before {p.followup}. "
            f"Consider offering to help with {p.followup}. "
            f"(confidence={p.confidence:.2f}; fluid — surface only if "
            f"contextually relevant; never auto-execute.)"
        )


# ---------------------------------------------------------------------------
# Process-wide singleton.
# ---------------------------------------------------------------------------

_engine: Optional[SuggestionEngine] = None


def get_suggestion_engine() -> SuggestionEngine:
    global _engine
    if _engine is None:
        _engine = SuggestionEngine()
    return _engine


def set_suggestion_engine(engine: SuggestionEngine) -> None:
    global _engine
    _engine = engine


def reset_suggestion_engine() -> None:
    global _engine
    _engine = None


__all__ = [
    "Suggestion",
    "SuggestionEngine",
    "get_suggestion_engine",
    "reset_suggestion_engine",
    "set_suggestion_engine",
]
