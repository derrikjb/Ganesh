"""Emotional context awareness: tone detection + personality trait adjustment.

The :class:`EmotionAnalyzer` inspects the last few user messages (default 3),
classifies the dominant emotional tone (frustration, excitement, sadness, or
neutral) using a lightweight VADER sentiment model plus rule-based keyword
boosters, and maps the detected emotion to bounded personality-trait deltas.

Design constraints (Task 34 spec):
  - **No persistent emotional state.** Emotion is recomputed per request from
    the message window and never written to disk or memory.
  - **Text-only.** No voice/audio emotion detection.
  - **Bounded shifts.** Every delta is clamped to ``MUTATION_RATE_CAP``
    (±0.15) and respects locked traits when applied via
    :meth:`PersonalityEngine.apply_emotion_shifts`.
  - **Neutral → no shift.** When confidence is below the threshold or the
    dominant tone is ``neutral``, all deltas are zero.

The trait-shift mapping (matching the Task 34 falsifiable spec):

    Frustration → verbosity -0.10, warmth -0.05, assertiveness +0.10
    Excitement   → warmth +0.10, humor +0.10
    Sadness      → warmth +0.10, humor -0.10
    Neutral      → (no shift)

Deltas are scaled by ``confidence`` so a weak signal produces a proportionally
smaller nudge, and the final value is clamped to the cap before reaching the
personality engine.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from ganesh_backend.services.personality import (
    PersonalityEngine,
    clamp,
    get_engine,
)


# ---------------------------------------------------------------------------
# Sentiment backend — VADER (pure Python, lexicon + rule based).
# ---------------------------------------------------------------------------

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer as _Vader  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - vaderSentiment is a declared dep.
    _Vader = None


_vader_instance: "_Vader | None" = None


def _get_vader() -> "_Vader | None":
    """Lazily instantiate the VADER analyzer (singleton, process-wide)."""
    global _vader_instance
    if _vader_instance is None and _Vader is not None:
        _vader_instance = _Vader()
    return _vader_instance


# ---------------------------------------------------------------------------
# Rule-based keyword boosters — sharpen VADER's general sentiment into the
# four target tones. Each pattern is case-insensitive.
# ---------------------------------------------------------------------------

_FRUSTRATION_TOKENS = re.compile(
    r"\b(ugh|argh|frustrated|annoying|annoyed|broken|isn'?t working|"
    r"doesn'?t work|not working|why is this|why does this|stupid|"
    r"useless|wtf|come on|seriously\?|again\?|still broken|"
    r"keep failing|keeps failing|giving up|fed up)\b",
    re.I,
)

_EXCITEMENT_TOKENS = re.compile(
    r"\b(awesome|amazing|love it|so good|incredible|fantastic|"
    r"excited|yay|woohoo|hell yes|this is great|perfect|"
    r"nailed it|beautiful|brilliant|stoked|hyped)\b",
    re.I,
)

_SADNESS_TOKENS = re.compile(
    r"\b(sad|depressed|depressing|heartbroken|devastated|terrible|"
    r"awful|horrible|miserable|lonely|grief|loss|lost|crying|tears|"
    r"hurts|hurting|painful|suffering|hopeless|exhausted|burnt out)\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Emotion → trait-delta mapping. Values are the *maximum* shift applied at
# confidence = 1.0; actual shifts are scaled by confidence and clamped to
# ``MUTATION_RATE_CAP`` before being applied.
# ---------------------------------------------------------------------------

EMOTION_TRAIT_DELTAS: dict[str, dict[str, float]] = {
    "frustration": {
        "verbosity": -0.10,
        "warmth": -0.05,
        "assertiveness": 0.10,
    },
    "excitement": {
        "warmth": 0.10,
        "humor": 0.10,
    },
    "sadness": {
        "warmth": 0.10,
        "humor": -0.10,
    },
    "neutral": {},
}

SUPPORTED_EMOTIONS: tuple[str, ...] = (
    "frustration",
    "excitement",
    "sadness",
    "neutral",
)

# Confidence threshold below which no shift is applied (neutral behaviour).
DEFAULT_CONFIDENCE_THRESHOLD = 0.6

# Number of trailing user messages considered for tone detection.
DEFAULT_MESSAGE_WINDOW = 3


@dataclass
class EmotionResult:
    """Outcome of an emotion-analysis pass.

    ``deltas`` are the *raw* (pre-clamp, pre-lock) trait shifts that would be
    applied at confidence = 1.0. The :meth:`PersonalityEngine.apply_emotion_shifts`
    method is responsible for scaling by confidence, clamping to the mutation
    cap, and skipping locked traits.
    """

    emotion: str
    confidence: float
    compound: float
    deltas: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "emotion": self.emotion,
            "confidence": self.confidence,
            "compound": self.compound,
            "deltas": dict(self.deltas),
        }


class EmotionAnalyzer:
    """Detect emotional tone from a window of user messages.

    Stateless beyond the lazily-initialised VADER singleton — safe to call
    concurrently from FastAPI's threadpool. No emotional state is persisted.
    """

    def __init__(
        self,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        message_window: int = DEFAULT_MESSAGE_WINDOW,
    ) -> None:
        self._confidence_threshold = float(confidence_threshold)
        self._message_window = max(1, int(message_window))

    # ---- public API -------------------------------------------------------

    def analyze(self, messages: Sequence[str]) -> EmotionResult:
        """Classify the dominant emotion in the trailing message window.

        Returns an :class:`EmotionResult` with ``confidence`` in ``[0, 1]``.
        When confidence is below the threshold the emotion is reported as
        ``neutral`` with zero deltas (so callers can apply unconditionally).
        """
        window = list(messages[-self._message_window :]) if messages else []
        text = " ".join(m for m in window if isinstance(m, str) and m.strip())
        if not text:
            return EmotionResult(
                emotion="neutral",
                confidence=0.0,
                compound=0.0,
                deltas={},
            )

        compound = self._vader_compound(text)
        scores = self._score_tones(text)

        emotion, confidence = self._classify(compound, scores)

        if emotion == "neutral" or confidence < self._confidence_threshold:
            return EmotionResult(
                emotion="neutral",
                confidence=confidence,
                compound=compound,
                deltas={},
            )

        deltas = dict(EMOTION_TRAIT_DELTAS.get(emotion, {}))
        return EmotionResult(
            emotion=emotion,
            confidence=confidence,
            compound=compound,
            deltas=deltas,
        )

    def analyze_and_shift(
        self,
        messages: Sequence[str],
        engine: PersonalityEngine | None = None,
    ) -> tuple[EmotionResult, dict[str, float]]:
        """Analyze ``messages`` and apply the resulting shifts to ``engine``.

        Returns the analysis result and the post-shift trait snapshot.
        Defaults to the process-wide :func:`get_engine` singleton.
        """
        eng = engine if engine is not None else get_engine()
        result = self.analyze(messages)
        traits = eng.apply_emotion_shifts(result.deltas, confidence=result.confidence)
        return result, traits

    # ---- internals --------------------------------------------------------

    def _vader_compound(self, text: str) -> float:
        vader = _get_vader()
        if vader is None:
            # Graceful degradation when vaderSentiment isn't installed (minimal CI).
            return 0.0
        return float(vader.polarity_scores(text)["compound"])

    def _score_tones(self, text: str) -> dict[str, int]:
        return {
            "frustration": len(_FRUSTRATION_TOKENS.findall(text)),
            "excitement": len(_EXCITEMENT_TOKENS.findall(text)),
            "sadness": len(_SADNESS_TOKENS.findall(text)),
        }

    def _classify(
        self, compound: float, scores: dict[str, int]
    ) -> tuple[str, float]:
        """Pick the dominant emotion and assign a confidence in [0, 1].

        Confidence blends VADER's |compound| (capped at 1.0) with a keyword
        boost: each matched keyword adds 0.15, up to 0.4 total. This keeps
        confidence > 0.6 only when both the sentiment polarity and the
        domain-specific tokens agree.
        """
        best_emotion = "neutral"
        best_score = 0
        for emotion in ("frustration", "excitement", "sadness"):
            if scores[emotion] > best_score:
                best_score = scores[emotion]
                best_emotion = emotion

        if best_emotion == "neutral":
            # No keyword signal — fall back to polarity-only classification.
            if compound <= -0.5:
                return "frustration", min(1.0, abs(compound))
            if compound >= 0.5:
                return "excitement", min(1.0, abs(compound))
            return "neutral", 1.0 - min(1.0, abs(compound))

        # Keyword signal present. Combine polarity magnitude + keyword boost.
        polarity_weight = abs(compound) if self._polarity_agrees(best_emotion, compound) else 0.3
        keyword_boost = min(0.4, best_score * 0.15)
        confidence = clamp(0.4 + polarity_weight * 0.4 + keyword_boost, 0.0, 1.0)
        return best_emotion, confidence

    @staticmethod
    def _polarity_agrees(emotion: str, compound: float) -> bool:
        if emotion == "frustration":
            return compound < 0.0
        if emotion == "excitement":
            return compound > 0.0
        if emotion == "sadness":
            return compound < 0.0
        return True


# ---------------------------------------------------------------------------
# Process-wide singleton (mirrors personality / profiles pattern).
# ---------------------------------------------------------------------------

_analyzer: EmotionAnalyzer | None = None


def get_analyzer() -> EmotionAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = EmotionAnalyzer()
    return _analyzer


def set_analyzer(analyzer: EmotionAnalyzer) -> None:
    global _analyzer
    _analyzer = analyzer


def reset_analyzer() -> None:
    global _analyzer
    _analyzer = None


def analyze_messages(messages: Sequence[str]) -> EmotionResult:
    """Convenience wrapper around the singleton analyzer."""
    return get_analyzer().analyze(messages)


__all__ = [
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "DEFAULT_MESSAGE_WINDOW",
    "EMOTION_TRAIT_DELTAS",
    "SUPPORTED_EMOTIONS",
    "EmotionAnalyzer",
    "EmotionResult",
    "analyze_messages",
    "get_analyzer",
    "reset_analyzer",
    "set_analyzer",
]
