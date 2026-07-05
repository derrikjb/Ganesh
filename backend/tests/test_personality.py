"""Tests for the PersonalityEngine trait matrix + dynamic shifting.

Five required tests:
  - test_trait_bounds          : values clamped to valid range
  - test_mutation_rate_cap     : max ±0.15 per shift
  - test_session_scoped_shift   : shifts not persisted to config
  - test_reset_to_baseline      : reset restores config values
  - test_locked_traits          : locked traits don't shift
"""
from __future__ import annotations

from typing import Any

import pytest

from ganesh_backend.services.personality import (
    DEFAULT_BASELINE,
    MUTATION_RATE_CAP,
    TRAIT_BOUNDS,
    PersonalityEngine,
)


class FakeConfig:
    """In-memory config service stub for PersonalityEngine tests."""

    def __init__(self, traits: dict[str, float] | None = None, locked: list[str] | None = None):
        self._store: dict[str, Any] = {
            "personality": {
                "traits": dict(traits) if traits is not None else dict(DEFAULT_BASELINE),
                "locked": list(locked) if locked is not None else [],
            }
        }
        self.save_calls: int = 0

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
        val = self._store
        for part in parts[:-1]:
            if part not in val or not isinstance(val[part], dict):
                val[part] = {}
            val = val[part]
        val[parts[-1]] = value


@pytest.fixture
def fake_config() -> FakeConfig:
    return FakeConfig()


def test_trait_bounds(fake_config: FakeConfig) -> None:
    """Trait values are always clamped to their valid bounds."""
    eng = PersonalityEngine(config=fake_config)

    # Direct set_trait clamps to [low, high].
    eng.set_trait("formality", 5.0)
    assert eng.get_traits()["formality"] == 1.0
    eng.set_trait("formality", -5.0)
    assert eng.get_traits()["formality"] == -1.0
    eng.set_trait("warmth", 10.0)
    assert eng.get_traits()["warmth"] == 1.0
    eng.set_trait("warmth", -1.0)
    assert eng.get_traits()["warmth"] == 0.0
    eng.set_trait("humor", 0.5)
    assert eng.get_traits()["humor"] == 0.5

    # update_traits clamps in bulk.
    eng.update_traits({"verbosity": 99.0, "assertiveness": -99.0})
    assert eng.get_traits()["verbosity"] == 1.0
    assert eng.get_traits()["assertiveness"] == -1.0

    # Every trait stays within its declared bounds after arbitrary shifts.
    for _ in range(50):
        eng.shift_traits({"message": "dear regards sincerely please kindly furthermore accordingly" * 10})
    for trait, value in eng.get_traits().items():
        low, high = TRAIT_BOUNDS[trait]
        assert low <= value <= high, f"{trait}={value} out of [{low}, {high}]"


def test_mutation_rate_cap(fake_config: FakeConfig) -> None:
    """No single shift may move a trait by more than ±MUTATION_RATE_CAP."""
    eng = PersonalityEngine(config=fake_config)

    # Start from a known baseline.
    before = eng.get_traits()
    # A context heavily loaded with formal tokens would naively push formality
    # far positive, but the cap limits the per-shift delta.
    eng.shift_traits(
        {"message": "dear regards sincerely please kindly furthermore accordingly " * 20}
    )
    after = eng.get_traits()
    for trait in TRAIT_BOUNDS:
        delta = after[trait] - before[trait]
        assert abs(delta) <= MUTATION_RATE_CAP + 1e-9, (
            f"{trait} shifted by {delta}, exceeding ±{MUTATION_RATE_CAP}"
        )

    # Repeated shifts accumulate but each individual call is capped.
    before2 = eng.get_traits()
    eng.shift_traits(
        {"message": "dear regards sincerely please kindly furthermore accordingly " * 20}
    )
    after2 = eng.get_traits()
    for trait in TRAIT_BOUNDS:
        delta = after2[trait] - before2[trait]
        assert abs(delta) <= MUTATION_RATE_CAP + 1e-9


def test_session_scoped_shift(fake_config: FakeConfig) -> None:
    """Shifts are session-scoped: config.yaml is never modified by shifting."""
    eng = PersonalityEngine(config=fake_config)
    original_config_traits = dict(fake_config._store["personality"]["traits"])

    eng.shift_traits({"message": "hey yo sup cheers lol btw ok"})
    eng.shift_traits({"message": "love great wonderful amazing happy glad" * 5})

    # The engine's current traits have moved...
    current = eng.get_traits()
    assert current != original_config_traits

    # ...but the underlying config store is untouched.
    assert fake_config._store["personality"]["traits"] == original_config_traits
    assert fake_config.save_calls == 0

    # A fresh engine instance reads the original baseline, not the shifts.
    eng2 = PersonalityEngine(config=fake_config)
    assert eng2.get_traits() == original_config_traits
    assert eng2.get_baseline() == original_config_traits


def test_reset_to_baseline(fake_config: FakeConfig) -> None:
    """reset_traits() restores all traits to the config baseline."""
    custom = {"formality": 0.3, "verbosity": -0.2, "warmth": 0.8, "humor": 0.1, "assertiveness": 0.4}
    fake_config._store["personality"]["traits"] = dict(custom)

    eng = PersonalityEngine(config=fake_config)
    assert eng.get_traits() == custom

    # Drift the traits via direct set + shifts.
    eng.set_trait("formality", -1.0)
    eng.shift_traits({"message": "hey yo sup cheers lol btw ok"})
    drifted = eng.get_traits()
    assert drifted != custom

    # Reset returns to the config baseline, not the DEFAULT_BASELINE.
    eng.reset_traits()
    assert eng.get_traits() == custom
    assert eng.get_baseline() == custom


def test_locked_traits(fake_config: FakeConfig) -> None:
    """Locked traits do not shift; unlocked traits do."""
    fake_config._store["personality"]["locked"] = ["formality"]
    eng = PersonalityEngine(config=fake_config)

    assert eng.is_locked("formality")
    assert not eng.is_locked("warmth")

    before = eng.get_traits()
    # Context that nudges multiple unlocked traits (warmth, humor, verbosity).
    eng.shift_traits(
        {"message": "love great wonderful amazing happy glad joke funny haha explain detail elaborate " * 10}
    )
    after = eng.get_traits()

    # Locked trait unchanged.
    assert after["formality"] == before["formality"]
    # At least one unlocked trait moved.
    moved = [t for t in TRAIT_BOUNDS if t != "formality" and abs(after[t] - before[t]) > 1e-9]
    assert len(moved) >= 1, "expected at least one unlocked trait to shift"

    # Unlocking allows shifting again.
    eng.unlock_trait("formality")
    assert not eng.is_locked("formality")
    before2 = eng.get_traits()
    eng.shift_traits(
        {"message": "dear regards sincerely please kindly furthermore accordingly " * 10}
    )
    after2 = eng.get_traits()
    assert abs(after2["formality"] - before2["formality"]) > 1e-9

    # Re-locking freezes it at the current value.
    eng.lock_trait("formality")
    frozen = eng.get_traits()["formality"]
    eng.shift_traits(
        {"message": "dear regards sincerely please kindly furthermore accordingly " * 10}
    )
    assert eng.get_traits()["formality"] == frozen
