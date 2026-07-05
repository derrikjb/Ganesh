"""Tests for the PersonalityEngine trait matrix + dynamic shifting + persistence."""
from __future__ import annotations

from pathlib import Path
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
def fake_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeConfig:
    monkeypatch.setenv("GANESH_DATA_DIR", str(tmp_path))
    return FakeConfig()


@pytest.fixture
def persistence_path(tmp_path: Path) -> Path:
    return tmp_path / "personality.json"


def test_trait_bounds(fake_config: FakeConfig, persistence_path: Path) -> None:
    """Trait values are always clamped to their valid bounds."""
    eng = PersonalityEngine(config=fake_config, persistence_path=persistence_path)

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

    eng.update_traits({"verbosity": 99.0, "assertiveness": -99.0})
    assert eng.get_traits()["verbosity"] == 1.0
    assert eng.get_traits()["assertiveness"] == -1.0

    for _ in range(50):
        eng.shift_traits({"message": "dear regards sincerely please kindly furthermore accordingly" * 10})
    for trait, value in eng.get_traits().items():
        low, high = TRAIT_BOUNDS[trait]
        assert low <= value <= high, f"{trait}={value} out of [{low}, {high}]"


def test_mutation_rate_cap(fake_config: FakeConfig, persistence_path: Path) -> None:
    """No single shift may move a trait by more than ±MUTATION_RATE_CAP."""
    eng = PersonalityEngine(config=fake_config, persistence_path=persistence_path)

    before = eng.get_traits()
    eng.shift_traits(
        {"message": "dear regards sincerely please kindly furthermore accordingly " * 20}
    )
    after = eng.get_traits()
    for trait in TRAIT_BOUNDS:
        delta = after[trait] - before[trait]
        assert abs(delta) <= MUTATION_RATE_CAP + 1e-9, (
            f"{trait} shifted by {delta}, exceeding ±{MUTATION_RATE_CAP}"
        )

    before2 = eng.get_traits()
    eng.shift_traits(
        {"message": "dear regards sincerely please kindly furthermore accordingly " * 20}
    )
    after2 = eng.get_traits()
    for trait in TRAIT_BOUNDS:
        delta = after2[trait] - before2[trait]
        assert abs(delta) <= MUTATION_RATE_CAP + 1e-9


def test_session_scoped_shift(fake_config: FakeConfig, persistence_path: Path) -> None:
    """Shifts are session-scoped: config.yaml is never modified by shifting."""
    eng = PersonalityEngine(config=fake_config, persistence_path=persistence_path)
    original_config_traits = dict(fake_config._store["personality"]["traits"])

    eng.shift_traits({"message": "hey yo sup cheers lol btw ok"})
    eng.shift_traits({"message": "love great wonderful amazing happy glad" * 5})

    current = eng.get_traits()
    assert current != original_config_traits

    assert fake_config._store["personality"]["traits"] == original_config_traits
    assert fake_config.save_calls == 0

    eng2 = PersonalityEngine(config=fake_config, persistence_path=persistence_path)
    assert eng2.get_traits() == original_config_traits
    assert eng2.get_baseline() == original_config_traits


def test_reset_to_baseline(fake_config: FakeConfig, persistence_path: Path) -> None:
    """reset_traits() restores all traits to the persisted baseline (config if no file)."""
    custom = {"formality": 0.3, "verbosity": -0.2, "warmth": 0.8, "humor": 0.1, "assertiveness": 0.4}
    fake_config._store["personality"]["traits"] = dict(custom)

    eng = PersonalityEngine(config=fake_config, persistence_path=persistence_path)
    assert eng.get_traits() == custom

    eng.set_trait("formality", -1.0)
    eng.shift_traits({"message": "hey yo sup cheers lol btw ok"})
    drifted = eng.get_traits()
    assert drifted != custom

    eng.reset_traits()
    assert eng.get_traits() == custom
    assert eng.get_baseline() == custom


def test_locked_traits(fake_config: FakeConfig, persistence_path: Path) -> None:
    """Locked traits do not shift; unlocked traits do."""
    fake_config._store["personality"]["locked"] = ["formality"]
    eng = PersonalityEngine(config=fake_config, persistence_path=persistence_path)

    assert eng.is_locked("formality")
    assert not eng.is_locked("warmth")

    before = eng.get_traits()
    eng.shift_traits(
        {"message": "love great wonderful amazing happy glad joke funny haha explain detail elaborate " * 10}
    )
    after = eng.get_traits()

    assert after["formality"] == before["formality"]
    moved = [t for t in TRAIT_BOUNDS if t != "formality" and abs(after[t] - before[t]) > 1e-9]
    assert len(moved) >= 1, "expected at least one unlocked trait to shift"

    eng.unlock_trait("formality")
    assert not eng.is_locked("formality")
    before2 = eng.get_traits()
    eng.shift_traits(
        {"message": "dear regards sincerely please kindly furthermore accordingly " * 10}
    )
    after2 = eng.get_traits()
    assert abs(after2["formality"] - before2["formality"]) > 1e-9

    eng.lock_trait("formality")
    frozen = eng.get_traits()["formality"]
    eng.shift_traits(
        {"message": "dear regards sincerely please kindly furthermore accordingly " * 10}
    )
    assert eng.get_traits()["formality"] == frozen


# ---- Persistence tests ----------------------------------------------------


def test_persisted_traits_survive_reload(fake_config: FakeConfig, persistence_path: Path) -> None:
    """Set traits, save, create new engine, assert traits restored."""
    eng = PersonalityEngine(config=fake_config, persistence_path=persistence_path)
    eng.update_traits({"warmth": 0.9, "humor": 0.7, "formality": 0.5}, persist=True)

    assert persistence_path.exists()

    eng2 = PersonalityEngine(config=fake_config, persistence_path=persistence_path)
    assert eng2.get_traits()["warmth"] == 0.9
    assert eng2.get_traits()["humor"] == 0.7
    assert eng2.get_traits()["formality"] == 0.5
    assert eng2.get_baseline() == eng2.get_traits()


def test_locked_traits_persisted(fake_config: FakeConfig, persistence_path: Path) -> None:
    """Lock a trait, save, reload, assert still locked."""
    eng = PersonalityEngine(config=fake_config, persistence_path=persistence_path)
    eng.lock_trait("formality", persist=True)
    eng.lock_trait("warmth", persist=True)

    eng2 = PersonalityEngine(config=fake_config, persistence_path=persistence_path)
    assert eng2.is_locked("formality")
    assert eng2.is_locked("warmth")
    assert not eng2.is_locked("humor")


def test_shifts_not_persisted(fake_config: FakeConfig, persistence_path: Path) -> None:
    """Shift traits, save, assert saved values are baseline (not shifted)."""
    import json

    eng = PersonalityEngine(config=fake_config, persistence_path=persistence_path)
    baseline_before = eng.get_baseline()

    eng.shift_traits(
        {"message": "dear regards sincerely please kindly furthermore accordingly " * 20}
    )
    shifted = eng.get_traits()
    assert shifted != baseline_before

    eng.save()

    saved = json.loads(persistence_path.read_text(encoding="utf-8"))
    saved_traits = saved["traits"]
    for trait in TRAIT_BOUNDS:
        assert saved_traits[trait] == baseline_before[trait], (
            f"{trait}: saved={saved_traits[trait]}, baseline={baseline_before[trait]}"
        )


def test_load_discards_unsaved_shifts(fake_config: FakeConfig, persistence_path: Path) -> None:
    """Shift, load, assert back to saved baseline."""
    eng = PersonalityEngine(config=fake_config, persistence_path=persistence_path)
    eng.update_traits({"warmth": 0.8}, persist=True)
    saved_state = eng.get_traits()

    eng.shift_traits(
        {"message": "dear regards sincerely please kindly furthermore accordingly " * 20}
    )
    shifted = eng.get_traits()
    assert shifted != saved_state

    eng.load()
    assert eng.get_traits() == saved_state
    assert eng.get_baseline() == saved_state


def test_save_load_api_endpoints(
    fake_config: FakeConfig,
    persistence_path: Path,
) -> None:
    """Hit POST /save and POST /load via TestClient."""
    from fastapi.testclient import TestClient

    from main import create_app  # noqa: E402
    from ganesh_backend.services.personality import set_engine, reset_engine

    test_engine = PersonalityEngine(config=fake_config, persistence_path=persistence_path)
    set_engine(test_engine)

    app = create_app()
    client = TestClient(app)

    # Persisted update: baseline + disk are updated.
    put_resp = client.put(
        "/api/personality/traits",
        json={"traits": {"warmth": 0.9}},
        params={"persist": "true"},
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["traits"]["warmth"] == 0.9
    assert put_resp.json()["persisted"] is True
    assert persistence_path.exists()

    # Explicit save endpoint.
    save_resp = client.post("/api/personality/save")
    assert save_resp.status_code == 200
    assert save_resp.json()["persisted"] is True

    # Transient update: only current moves, baseline + disk untouched.
    transient_resp = client.put(
        "/api/personality/traits",
        json={"traits": {"warmth": 0.1}},
        params={"persist": "false"},
    )
    assert transient_resp.status_code == 200
    assert transient_resp.json()["traits"]["warmth"] == 0.1

    # Shift drifts current further away from the saved baseline.
    test_engine.shift_traits(
        {"message": "urgent asap immediately now error broken fail wrong " * 20}
    )
    shifted = test_engine.get_traits()["warmth"]
    assert shifted != 0.9

    # Load discards unsaved shifts + transient edits, restores saved baseline.
    load_resp = client.post("/api/personality/load")
    assert load_resp.status_code == 200
    assert load_resp.json()["traits"]["warmth"] == 0.9

    reset_engine()
