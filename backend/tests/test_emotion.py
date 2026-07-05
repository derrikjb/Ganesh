"""Tests for emotional context awareness (Task 34): tone detection + trait shifts."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ganesh_backend.services.emotion import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    EMOTION_TRAIT_DELTAS,
    EmotionAnalyzer,
    EmotionResult,
    get_analyzer,
    reset_analyzer,
    set_analyzer,
)
from ganesh_backend.services.personality import (
    DEFAULT_BASELINE,
    MUTATION_RATE_CAP,
    PersonalityEngine,
)


class FakeConfig:
    def __init__(
        self,
        traits: dict[str, float] | None = None,
        locked: list[str] | None = None,
    ) -> None:
        self._store: dict[str, Any] = {
            "personality": {
                "traits": dict(traits) if traits is not None else dict(DEFAULT_BASELINE),
                "locked": list(locked) if locked is not None else [],
            }
        }

    def get_setting(self, key: str, default: Any = None) -> Any:
        parts = key.split(".")
        val: Any = self._store
        for part in parts:
            if isinstance(val, dict) and part in val:
                val = val[part]
            else:
                return default
        return val

    def set_setting(self, key: str, value: Any) -> None:
        parts = key.split(".")
        val: Any = self._store
        for part in parts[:-1]:
            if part not in val or not isinstance(val[part], dict):
                val[part] = {}
            val = val[part]
        val[parts[-1]] = value


@pytest.fixture
def fake_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeConfig:
    monkeypatch.setenv("GANESH_DATA_DIR", str(tmp_path))
    return FakeConfig()


@pytest.fixture
def persistence_path(tmp_path: Path) -> Path:
    return tmp_path / "personality.json"


@pytest.fixture
def engine(
    fake_config: FakeConfig, persistence_path: Path
) -> PersonalityEngine:
    return PersonalityEngine(config=fake_config, persistence_path=persistence_path)


@pytest.fixture(autouse=True)
def _reset_analyzer_singleton() -> None:
    reset_analyzer()
    yield
    reset_analyzer()


FRUSTRATED_MESSAGES = [
    "hey can you help me",
    "this isn't working",
    "ugh why is this broken",
]

EXCITED_MESSAGES = [
    "ok let's try",
    "oh that's awesome",
    "love it this is great",
]

SAD_MESSAGES = [
    "thanks",
    "i've been feeling sad today",
    "it's been a terrible week and i'm exhausted",
]

NEUTRAL_MESSAGES = [
    "what is the capital of france",
    "please summarize the document",
    "list the steps to configure the tool",
]


# ---------------------------------------------------------------------------
# test_frustration_detection
# ---------------------------------------------------------------------------


def test_frustration_detection(engine: PersonalityEngine) -> None:
    analyzer = EmotionAnalyzer()
    result = analyzer.analyze(FRUSTRATED_MESSAGES)

    assert result.emotion == "frustration"
    assert result.confidence > 0.6, (
        f"expected frustration confidence > 0.6, got {result.confidence}"
    )

    deltas = EMOTION_TRAIT_DELTAS["frustration"]
    assert result.deltas == deltas

    before = engine.get_traits()
    after = engine.apply_emotion_shifts(result.deltas, confidence=result.confidence)

    assert after["verbosity"] < before["verbosity"], "frustration should reduce verbosity"
    assert after["warmth"] <= before["warmth"], "frustration should not increase warmth"
    assert after["assertiveness"] > before["assertiveness"], (
        "frustration should increase assertiveness"
    )

    verbosity_delta = after["verbosity"] - before["verbosity"]
    assert abs(verbosity_delta) <= MUTATION_RATE_CAP + 1e-9
    assert verbosity_delta < 0


# ---------------------------------------------------------------------------
# test_excitement_detection
# ---------------------------------------------------------------------------


def test_excitement_detection(engine: PersonalityEngine) -> None:
    analyzer = EmotionAnalyzer()
    result = analyzer.analyze(EXCITED_MESSAGES)

    assert result.emotion == "excitement"
    assert result.confidence > 0.6, (
        f"expected excitement confidence > 0.6, got {result.confidence}"
    )

    deltas = EMOTION_TRAIT_DELTAS["excitement"]
    assert result.deltas == deltas

    before = engine.get_traits()
    after = engine.apply_emotion_shifts(result.deltas, confidence=result.confidence)

    assert after["warmth"] > before["warmth"], "excitement should increase warmth"
    assert after["humor"] > before["humor"], "excitement should increase humor"

    warmth_delta = after["warmth"] - before["warmth"]
    assert warmth_delta <= MUTATION_RATE_CAP + 1e-9


# ---------------------------------------------------------------------------
# test_neutral_no_shift
# ---------------------------------------------------------------------------


def test_neutral_no_shift(engine: PersonalityEngine) -> None:
    analyzer = EmotionAnalyzer()
    result = analyzer.analyze(NEUTRAL_MESSAGES)

    assert result.emotion == "neutral"
    assert result.deltas == {}

    before = engine.get_traits()
    after = engine.apply_emotion_shifts(result.deltas, confidence=result.confidence)
    assert after == before, "neutral emotion must not shift any trait"


def test_empty_messages_no_shift(engine: PersonalityEngine) -> None:
    analyzer = EmotionAnalyzer()
    result = analyzer.analyze([])

    assert result.emotion == "neutral"
    assert result.confidence == 0.0
    assert result.deltas == {}

    before = engine.get_traits()
    after = engine.apply_emotion_shifts(result.deltas, confidence=result.confidence)
    assert after == before


# ---------------------------------------------------------------------------
# test_emotion_respects_locks
# ---------------------------------------------------------------------------


def test_emotion_respects_locks(
    fake_config: FakeConfig, persistence_path: Path
) -> None:
    fake_config._store["personality"]["locked"] = ["verbosity", "assertiveness"]
    eng = PersonalityEngine(config=fake_config, persistence_path=persistence_path)

    analyzer = EmotionAnalyzer()
    result = analyzer.analyze(FRUSTRATED_MESSAGES)
    assert result.emotion == "frustration"

    before = eng.get_traits()
    after = eng.apply_emotion_shifts(result.deltas, confidence=result.confidence)

    assert after["verbosity"] == before["verbosity"], "locked verbosity must not shift"
    assert after["assertiveness"] == before["assertiveness"], (
        "locked assertiveness must not shift"
    )
    assert after["warmth"] <= before["warmth"], (
        "unlocked warmth should still shift (decrease for frustration)"
    )


# ---------------------------------------------------------------------------
# test_emotion_bounded_by_cap
# ---------------------------------------------------------------------------


def test_emotion_bounded_by_cap(engine: PersonalityEngine) -> None:
    analyzer = EmotionAnalyzer()

    result = analyzer.analyze(FRUSTRATED_MESSAGES)
    assert result.emotion == "frustration"

    before = engine.get_traits()
    engine.apply_emotion_shifts(result.deltas, confidence=1.0)
    after_one = engine.get_traits()
    for trait in before:
        delta = after_one[trait] - before[trait]
        assert abs(delta) <= MUTATION_RATE_CAP + 1e-9, (
            f"{trait} shifted by {delta}, exceeding ±{MUTATION_RATE_CAP}"
        )

    engine.apply_emotion_shifts(result.deltas, confidence=1.0)
    after_two = engine.get_traits()
    for trait in before:
        delta = after_two[trait] - after_one[trait]
        assert abs(delta) <= MUTATION_RATE_CAP + 1e-9, (
            f"{trait} second shift {delta} exceeded ±{MUTATION_RATE_CAP}"
        )


def test_emotion_bounded_by_cap_large_delta(engine: PersonalityEngine) -> None:
    before = engine.get_traits()

    engine.apply_emotion_shifts(
        {"verbosity": -10.0, "warmth": -10.0, "assertiveness": 10.0},
        confidence=1.0,
    )
    after = engine.get_traits()
    for trait in before:
        delta = after[trait] - before[trait]
        assert abs(delta) <= MUTATION_RATE_CAP + 1e-9, (
            f"{trait} shifted by {delta} despite huge input delta"
        )


# ---------------------------------------------------------------------------
# Additional coverage: sadness, confidence scaling, singleton, router.
# ---------------------------------------------------------------------------


def test_sadness_detection(engine: PersonalityEngine) -> None:
    analyzer = EmotionAnalyzer()
    result = analyzer.analyze(SAD_MESSAGES)

    assert result.emotion == "sadness"
    assert result.confidence > 0.6, (
        f"expected sadness confidence > 0.6, got {result.confidence}"
    )

    before = engine.get_traits()
    after = engine.apply_emotion_shifts(result.deltas, confidence=result.confidence)
    assert after["warmth"] > before["warmth"], "sadness should increase warmth"
    assert after["humor"] < before["humor"], "sadness should decrease humor"


def test_confidence_scales_shift(engine: PersonalityEngine) -> None:
    analyzer = EmotionAnalyzer()
    result = analyzer.analyze(FRUSTRATED_MESSAGES)
    assert result.confidence > 0.6

    before = engine.get_traits()
    full = engine.apply_emotion_shifts(result.deltas, confidence=1.0)
    full_delta = full["assertiveness"] - before["assertiveness"]

    engine.reset_traits()
    before2 = engine.get_traits()
    half = engine.apply_emotion_shifts(result.deltas, confidence=0.5)
    half_delta = half["assertiveness"] - before2["assertiveness"]

    assert abs(half_delta) < abs(full_delta), (
        "lower confidence should produce a smaller shift"
    )


def test_singleton_get_set_reset() -> None:
    a1 = get_analyzer()
    a2 = get_analyzer()
    assert a1 is a2

    custom = EmotionAnalyzer(confidence_threshold=0.9, message_window=5)
    set_analyzer(custom)
    assert get_analyzer() is custom

    reset_analyzer()
    fresh = get_analyzer()
    assert fresh is not custom
    assert fresh._confidence_threshold == DEFAULT_CONFIDENCE_THRESHOLD  # noqa: SLF001


def test_message_window_truncation() -> None:
    analyzer = EmotionAnalyzer(message_window=3)
    long_history = ["neutral question"] * 10 + FRUSTRATED_MESSAGES
    result = analyzer.analyze(long_history)
    assert result.emotion == "frustration"
    assert result.confidence > 0.6


def test_emotion_result_to_dict() -> None:
    result = EmotionResult(
        emotion="excitement",
        confidence=0.8,
        compound=0.5,
        deltas={"warmth": 0.1},
    )
    payload = result.to_dict()
    assert payload == {
        "emotion": "excitement",
        "confidence": 0.8,
        "compound": 0.5,
        "deltas": {"warmth": 0.1},
    }


def test_analyze_and_shift_returns_traits(engine: PersonalityEngine) -> None:
    analyzer = EmotionAnalyzer()
    result, traits = analyzer.analyze_and_shift(FRUSTRATED_MESSAGES, engine=engine)
    assert result.emotion == "frustration"
    assert traits == engine.get_traits()
    assert traits["assertiveness"] > engine.get_baseline()["assertiveness"]


# ---------------------------------------------------------------------------
# Router integration (FastAPI TestClient).
# ---------------------------------------------------------------------------


def test_emotion_router_endpoints(
    fake_config: FakeConfig,
    persistence_path: Path,
) -> None:
    from fastapi.testclient import TestClient

    from main import create_app
    from ganesh_backend.services.personality import set_engine, reset_engine

    test_engine = PersonalityEngine(
        config=fake_config, persistence_path=persistence_path
    )
    set_engine(test_engine)

    app = create_app()
    client = TestClient(app)

    supported = client.get("/api/emotion/supported")
    assert supported.status_code == 200
    assert "frustration" in supported.json()["emotions"]

    analyze_resp = client.post("/api/emotion/analyze", json={"messages": FRUSTRATED_MESSAGES})
    assert analyze_resp.status_code == 200
    body = analyze_resp.json()
    assert body["emotion"] == "frustration"
    assert body["confidence"] > 0.6

    shift_resp = client.post("/api/emotion/shift", json={"messages": FRUSTRATED_MESSAGES})
    assert shift_resp.status_code == 200
    sbody = shift_resp.json()
    assert sbody["analysis"]["emotion"] == "frustration"
    assert sbody["traits"]["assertiveness"] > sbody["baseline"]["assertiveness"]

    reset_engine()
