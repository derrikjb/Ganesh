"""Personality trait matrix with dynamic context-based shifting.

The PersonalityEngine maintains a set of five traits loaded from the user's
config.yaml (under ``personality.traits``). Traits are clamped to their valid
bounds, can be temporarily shifted based on conversation context (session
scoped, never persisted), locked against shifting, and reset to the config
baseline. The current trait values are injected into the LLM system prompt via
``get_system_prompt()``.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from ganesh_backend.services.config import config_service


# Trait bounds: (min, max). Some traits are bipolar [-1.0, 1.0], others are
# unipolar [0.0, 1.0]. This asymmetry is intentional and matches the spec.
TRAIT_BOUNDS: dict[str, tuple[float, float]] = {
    "formality": (-1.0, 1.0),
    "verbosity": (-1.0, 1.0),
    "warmth": (0.0, 1.0),
    "humor": (0.0, 1.0),
    "assertiveness": (-1.0, 1.0),
}

# Maximum absolute change applied to any single trait during one shift call.
# Prevents drastic personality swings from a single context signal.
MUTATION_RATE_CAP = 0.15

# Default baseline traits used when config.yaml has no personality section.
DEFAULT_BASELINE: dict[str, float] = {
    "formality": 0.0,
    "verbosity": 0.0,
    "warmth": 0.5,
    "humor": 0.3,
    "assertiveness": 0.0,
}


def clamp(value: float, low: float, high: float) -> float:
    """Clamp ``value`` to ``[low, high]``."""
    if value < low:
        return low
    if value > high:
        return high
    return value


def _clamp_trait(trait: str, value: float) -> float:
    low, high = TRAIT_BOUNDS[trait]
    return clamp(float(value), low, high)


# Lightweight context signal heuristics. Each keyword contributes a small
# nudge to a trait; the aggregate nudge is clamped to ±MUTATION_RATE_CAP and
# then applied to the current trait value (which is itself clamped to bounds).
# These are intentionally simple, deterministic rules — Task 35 handles
# proactive learning from interactions.
_CASUAL_TOKENS = re.compile(r"\b(hi|hey|yo|sup|cheers|thanks|lol|btw|ok|okay)\b", re.I)
_FORMAL_TOKENS = re.compile(r"\b(dear|regards|sincerely|please|kindly|furthermore|accordingly)\b", re.I)
_WARM_TOKENS = re.compile(r"\b(love|great|wonderful|amazing|happy|glad|hope|thank you)\b", re.I)
_COLD_TOKENS = re.compile(r"\b(urgent|asap|immediately|now|error|broken|fail|wrong|broken)\b", re.I)
_HUMOR_TOKENS = re.compile(r"\b(joke|funny|lol|haha|pun|silly|hilarious)\b", re.I)
_SERIOUS_TOKENS = re.compile(r"\b(serious|important|critical|production|deadline|legal|contract)\b", re.I)
_ASSERTIVE_TOKENS = re.compile(r"\b(must|need|required|do this|make sure|ensure|i want)\b", re.I)
_DEFERENTIAL_TOKENS = re.compile(r"\b(could you|would you mind|if possible|perhaps|maybe|sorry)\b", re.I)
_VERBOSE_TOKENS = re.compile(r"\b(explain|detail|elaborate|in depth|comprehensive|step by step)\b", re.I)
_CONCISE_TOKENS = re.compile(r"\b(brief|short|summary|tldr|quick|bullet)\b", re.I)


def _analyze_context(context: Mapping[str, Any]) -> dict[str, float]:
    """Compute raw trait deltas from conversation context.

    Returns a dict of trait -> delta in [-MUTATION_RATE_CAP, +MUTATION_RATE_CAP].
    """
    text = ""
    if isinstance(context, dict):
        msg = context.get("message") or context.get("text") or ""
        if isinstance(msg, str):
            text = msg
        # Task type can bias verbosity: coding/research → more verbose.
        task_type = context.get("task_type") or ""
        if isinstance(task_type, str):
            text = f"{text} {task_type}"

    deltas: dict[str, float] = {t: 0.0 for t in TRAIT_BOUNDS}

    def _count(pattern: re.Pattern[str]) -> int:
        return len(pattern.findall(text))

    casual, formal = _count(_CASUAL_TOKENS), _count(_FORMAL_TOKENS)
    warm, cold = _count(_WARM_TOKENS), _count(_COLD_TOKENS)
    humor, serious = _count(_HUMOR_TOKENS), _count(_SERIOUS_TOKENS)
    assertive, deferential = _count(_ASSERTIVE_TOKENS), _count(_DEFERENTIAL_TOKENS)
    verbose, concise = _count(_VERBOSE_TOKENS), _count(_CONCISE_TOKENS)

    deltas["formality"] = float(formal - casual)
    deltas["verbosity"] = float(verbose - concise)
    deltas["warmth"] = float(warm - cold)
    deltas["humor"] = float(humor - serious)
    deltas["assertiveness"] = float(assertive - deferential)

    # Normalize each delta to [-MUTATION_RATE_CAP, +MUTATION_RATE_CAP].
    for trait in deltas:
        raw = deltas[trait]
        if raw > 0:
            deltas[trait] = min(raw * 0.05, MUTATION_RATE_CAP)
        else:
            deltas[trait] = max(raw * 0.05, -MUTATION_RATE_CAP)
    return deltas


class PersonalityEngine:
    """Session-scoped personality trait matrix with dynamic shifting.

    Baseline traits are loaded from config.yaml (``personality.traits``).
    Shifts are kept in-memory only and never written back to config.
    """

    def __init__(self, config: Any = None) -> None:
        # Allow injecting a config_service (for testing); default to the global.
        self._config = config if config is not None else config_service
        self._baseline: dict[str, float] = self._load_baseline()
        self._current: dict[str, float] = dict(self._baseline)
        self._locked: set[str] = set(self._load_locked())

    # ---- baseline loading -------------------------------------------------

    def _load_baseline(self) -> dict[str, float]:
        traits_cfg = self._config.get_setting("personality.traits", {}) or {}
        baseline: dict[str, float] = {}
        for trait, bounds in TRAIT_BOUNDS.items():
            raw = traits_cfg.get(trait, DEFAULT_BASELINE[trait]) if isinstance(traits_cfg, Mapping) else DEFAULT_BASELINE[trait]
            try:
                baseline[trait] = _clamp_trait(trait, float(raw))
            except (TypeError, ValueError):
                baseline[trait] = DEFAULT_BASELINE[trait]
        return baseline

    def _load_locked(self) -> list[str]:
        locked = self._config.get_setting("personality.locked", []) or []
        if not isinstance(locked, list):
            return []
        return [str(t) for t in locked if t in TRAIT_BOUNDS]

    # ---- public API -------------------------------------------------------

    def get_traits(self) -> dict[str, float]:
        """Return current trait values (baseline + session shifts)."""
        return dict(self._current)

    def get_baseline(self) -> dict[str, float]:
        """Return the config baseline traits."""
        return dict(self._baseline)

    def set_trait(self, trait: str, value: float) -> float:
        """Set a trait directly (clamped). Does not persist to config."""
        if trait not in TRAIT_BOUNDS:
            raise KeyError(f"Unknown trait: {trait!r}")
        clamped = _clamp_trait(trait, value)
        self._current[trait] = clamped
        return clamped

    def update_traits(self, updates: Mapping[str, float]) -> dict[str, float]:
        """Update multiple traits at once (clamped). Does not persist."""
        result: dict[str, float] = {}
        for trait, value in updates.items():
            if trait not in TRAIT_BOUNDS:
                raise KeyError(f"Unknown trait: {trait!r}")
            result[trait] = self.set_trait(trait, value)
        return result

    def lock_trait(self, trait: str) -> None:
        if trait not in TRAIT_BOUNDS:
            raise KeyError(f"Unknown trait: {trait!r}")
        self._locked.add(trait)

    def unlock_trait(self, trait: str) -> None:
        if trait not in TRAIT_BOUNDS:
            raise KeyError(f"Unknown trait: {trait!r}")
        self._locked.discard(trait)

    def is_locked(self, trait: str) -> bool:
        return trait in self._locked

    def locked_traits(self) -> list[str]:
        return sorted(self._locked)

    def reset_traits(self) -> dict[str, float]:
        """Restore all traits to the config baseline (clears shifts)."""
        self._current = dict(self._baseline)
        return dict(self._current)

    def shift_traits(self, context: Mapping[str, Any]) -> dict[str, float]:
        """Apply context-based temporary shifts to current traits.

        Each trait's change is capped at ±MUTATION_RATE_CAP and the resulting
        value is clamped to the trait's valid bounds. Locked traits are not
        shifted. Shifts are session-scoped (in-memory only).
        """
        deltas = _analyze_context(context)
        for trait, delta in deltas.items():
            if trait in self._locked:
                continue
            current = self._current[trait]
            # Cap the per-shift mutation.
            capped_delta = clamp(delta, -MUTATION_RATE_CAP, MUTATION_RATE_CAP)
            new_value = _clamp_trait(trait, current + capped_delta)
            self._current[trait] = new_value
        return dict(self._current)

    # ---- system prompt ----------------------------------------------------

    def get_system_prompt(self) -> str:
        """Build a system prompt fragment encoding the current trait values.

        The prompt is a concise description of the assistant's current
        personality, suitable for prepending to an LLM system message.
        """
        t = self._current
        return (
            "You are Ganesh, a local-first AI assistant. Adapt your tone to the "
            f"following personality traits (current values): "
            f"formality={t['formality']:.2f} "
            f"(-1.0 casual to 1.0 formal), "
            f"verbosity={t['verbosity']:.2f} "
            f"(-1.0 concise to 1.0 verbose), "
            f"warmth={t['warmth']:.2f} "
            f"(0.0 cold to 1.0 warm), "
            f"humor={t['humor']:.2f} "
            f"(0.0 serious to 1.0 playful), "
            f"assertiveness={t['assertiveness']:.2f} "
            f"(-1.0 deferential to 1.0 assertive). "
            "Stay within these traits while remaining helpful and accurate."
        )


# Module-level singleton for the router to use. Tests construct their own
# instances via PersonalityEngine(config=...) with a mocked config service.
engine = PersonalityEngine()
