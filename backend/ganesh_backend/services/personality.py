"""Personality trait matrix with dynamic context-based shifting + persistence.

The PersonalityEngine maintains five traits loaded from config.yaml
(``personality.traits``), optionally overridden by a persisted profile at
``~/.ganesh/personality.json`` (or ``$GANESH_DATA_DIR/personality.json``).

State layers:
  - ``_persisted_baseline`` : last saved profile (from disk, or config if no file).
                              Modified only by ``save()`` / ``load()``.
  - ``_baseline``           : working profile, modified by ``set_trait``.
                              What ``save()`` writes to disk.
  - ``_current``            : baseline + session-scoped context shifts (what the
                              LLM sees). Shifts never touch ``_baseline``.

``save()`` writes ``_baseline`` + ``_locked`` to disk and promotes it to
``_persisted_baseline``. ``load()`` reloads from disk, discarding unsaved
``set_trait`` changes and session shifts. ``reset_traits()`` restores
``_baseline`` and ``_current`` to ``_persisted_baseline``.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from ganesh_backend.services.config import config_service


TRAIT_BOUNDS: dict[str, tuple[float, float]] = {
    "formality": (-1.0, 1.0),
    "verbosity": (-1.0, 1.0),
    "warmth": (0.0, 1.0),
    "humor": (0.0, 1.0),
    "assertiveness": (-1.0, 1.0),
}

MUTATION_RATE_CAP = 0.15

DEFAULT_BASELINE: dict[str, float] = {
    "formality": 0.0,
    "verbosity": 0.0,
    "warmth": 0.5,
    "humor": 0.3,
    "assertiveness": 0.0,
}

PERSISTENCE_FILENAME = "personality.json"


def clamp(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def _get_mutation_rate_cap() -> float:
    return float(config_service.get_setting("personality.mutation_rate_cap", MUTATION_RATE_CAP))


def _get_mutation_scale() -> float:
    return float(config_service.get_setting("personality.mutation_scale", 0.05))


def _get_trait_bounds() -> dict[str, tuple[float, float]]:
    configured = config_service.get_setting("personality.trait_bounds", None)
    if not isinstance(configured, dict):
        return TRAIT_BOUNDS
    out: dict[str, tuple[float, float]] = {}
    for trait, bounds in TRAIT_BOUNDS.items():
        raw = configured.get(trait)
        if isinstance(raw, (list, tuple)) and len(raw) == 2:
            try:
                out[trait] = (float(raw[0]), float(raw[1]))
            except (TypeError, ValueError):
                out[trait] = bounds
        else:
            out[trait] = bounds
    return out


def _clamp_trait(trait: str, value: float) -> float:
    low, high = _get_trait_bounds()[trait]
    return clamp(float(value), low, high)


def _default_persistence_path() -> Path:
    env_dir = os.environ.get("GANESH_DATA_DIR")
    if env_dir:
        base = Path(env_dir)
    else:
        base = Path.home() / ".ganesh"
    return base / PERSISTENCE_FILENAME


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
    text = ""
    if isinstance(context, dict):
        msg = context.get("message") or context.get("text") or ""
        if isinstance(msg, str):
            text = msg
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

    for trait in deltas:
        raw = deltas[trait]
        scale = _get_mutation_scale()
        cap = _get_mutation_rate_cap()
        if raw > 0:
            deltas[trait] = min(raw * scale, cap)
        else:
            deltas[trait] = max(raw * scale, -cap)
    return deltas


class PersonalityEngine:
    """Personality trait matrix with persistence and dynamic shifting."""

    def __init__(
        self,
        config: Any = None,
        persistence_path: Path | None = None,
    ) -> None:
        self._config = config if config is not None else config_service
        self._persistence_path = persistence_path or _default_persistence_path()
        self._baseline: dict[str, float] = self._load_baseline()
        self._locked: set[str] = set(self._load_locked())
        self._load_persisted_state()
        self._persisted_baseline: dict[str, float] = dict(self._baseline)
        self._current: dict[str, float] = dict(self._baseline)

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

    def _load_persisted_state(self) -> None:
        try:
            if not self._persistence_path.exists():
                return
            with open(self._persistence_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        traits = data.get("traits", {})
        if isinstance(traits, dict):
            for trait in TRAIT_BOUNDS:
                if trait in traits:
                    try:
                        self._baseline[trait] = _clamp_trait(trait, float(traits[trait]))
                    except (TypeError, ValueError):
                        pass
        self._current = dict(self._baseline)
        locked = data.get("locked", [])
        if isinstance(locked, list):
            self._locked = {str(t) for t in locked if t in TRAIT_BOUNDS}

    # ---- persistence ------------------------------------------------------

    def save(self) -> None:
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "traits": dict(self._baseline),
            "locked": sorted(self._locked),
        }
        with open(self._persistence_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        self._persisted_baseline = dict(self._baseline)

    def load(self) -> None:
        self._baseline = self._load_baseline()
        self._locked = set(self._load_locked())
        self._load_persisted_state()
        self._persisted_baseline = dict(self._baseline)
        self._current = dict(self._baseline)

    def get_persistence_path(self) -> Path:
        return self._persistence_path

    def has_persisted_state(self) -> bool:
        return self._persistence_path.exists()

    def is_persisted(self) -> bool:
        return self._persistence_path.exists()

    @property
    def persistence_path(self) -> Path:
        return self._persistence_path

    # ---- public API -------------------------------------------------------

    def get_traits(self) -> dict[str, float]:
        return dict(self._current)

    def get_baseline(self) -> dict[str, float]:
        return dict(self._persisted_baseline)

    def set_trait(self, trait: str, value: float, persist: bool = False) -> float:
        if trait not in TRAIT_BOUNDS:
            raise KeyError(f"Unknown trait: {trait!r}")
        clamped = _clamp_trait(trait, value)
        self._baseline[trait] = clamped
        self._current[trait] = clamped
        if persist:
            self.save()
        return clamped

    def update_traits(
        self, updates: Mapping[str, float], persist: bool = False
    ) -> dict[str, float]:
        result: dict[str, float] = {}
        for trait, value in updates.items():
            if trait not in TRAIT_BOUNDS:
                raise KeyError(f"Unknown trait: {trait!r}")
            result[trait] = self.set_trait(trait, value, persist=persist)
        return result

    def lock_trait(self, trait: str, persist: bool = False) -> None:
        if trait not in TRAIT_BOUNDS:
            raise KeyError(f"Unknown trait: {trait!r}")
        self._locked.add(trait)
        if persist:
            self.save()

    def unlock_trait(self, trait: str, persist: bool = False) -> None:
        if trait not in TRAIT_BOUNDS:
            raise KeyError(f"Unknown trait: {trait!r}")
        self._locked.discard(trait)
        if persist:
            self.save()

    def is_locked(self, trait: str) -> bool:
        return trait in self._locked

    def locked_traits(self) -> list[str]:
        return sorted(self._locked)

    def reset_traits(self) -> dict[str, float]:
        self._baseline = dict(self._persisted_baseline)
        self._current = dict(self._persisted_baseline)
        return dict(self._current)

    def shift_traits(self, context: Mapping[str, Any]) -> dict[str, float]:
        deltas = _analyze_context(context)
        cap = _get_mutation_rate_cap()
        for trait, delta in deltas.items():
            if trait in self._locked:
                continue
            current = self._current[trait]
            capped_delta = clamp(delta, -cap, cap)
            new_value = _clamp_trait(trait, current + capped_delta)
            self._current[trait] = new_value
        return dict(self._current)

    def apply_emotion_shifts(
        self,
        deltas: Mapping[str, float],
        confidence: float = 1.0,
    ) -> dict[str, float]:
        """Apply emotion-derived trait deltas, respecting locks + mutation cap.

        Used by the emotion-awareness layer (Task 34). ``deltas`` are the
        raw per-trait shifts (e.g. ``{"verbosity": -0.10}``); they are scaled
        by ``confidence`` (clamped to [0, 1]) and then clamped to
        ``±MUTATION_RATE_CAP`` before being added to the current trait value.
        Locked traits are skipped entirely. No state is persisted.
        """
        conf = clamp(float(confidence), 0.0, 1.0)
        cap = _get_mutation_rate_cap()
        for trait, raw_delta in deltas.items():
            if trait not in TRAIT_BOUNDS or trait in self._locked:
                continue
            scaled = float(raw_delta) * conf
            capped_delta = clamp(scaled, -cap, cap)
            current = self._current[trait]
            self._current[trait] = _clamp_trait(trait, current + capped_delta)
        return dict(self._current)

    # ---- system prompt ----------------------------------------------------

    def get_system_prompt(self) -> str:
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


engine = PersonalityEngine()


def get_engine() -> PersonalityEngine:
    return engine


def set_engine(eng: PersonalityEngine) -> None:
    global engine
    engine = eng


def reset_engine() -> None:
    global engine
    engine = PersonalityEngine()
