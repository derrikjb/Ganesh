"""Tests for the model manager service.

Verifies:
    - check_models() detects missing vs present (and checksum-valid) models
    - download_model() reports correct progress (bytes downloaded / total)
    - SHA256 checksum is validated after download (mismatch raises)
    - Resume from a partial .part file uses HTTP Range and completes the file

All HTTP traffic is mocked via httpx.MockTransport — no real network access.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from pathlib import Path

import httpx
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from ganesh_backend.services.model_manager import (  # noqa: E402
    ModelManager,
    ModelSpec,
    REQUIRED_MODELS,
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    """Build an AsyncClient backed by a MockTransport handler."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def models_dir(tmp_path: Path) -> Path:
    d = tmp_path / "models"
    d.mkdir()
    return d


@pytest.fixture
def manager(models_dir: Path) -> ModelManager:
    return ModelManager(models_dir=models_dir)


def test_check_models_detects_missing(manager: ModelManager, models_dir: Path) -> None:
    """check_models() returns False for every required model when none are present."""
    status = manager.check_models()
    assert set(status.keys()) == set(REQUIRED_MODELS.keys())
    assert all(present is False for present in status.values()), (
        "All models should be missing in an empty directory"
    )


def test_check_models_detects_present(manager: ModelManager, models_dir: Path) -> None:
    """A model file with a matching checksum is reported as present."""
    spec = REQUIRED_MODELS["embeddings"]
    payload = b"embeddings-model-payload"
    digest = _sha256(payload)
    # Mutate the spec's checksum to match our test payload so check_models
    # validates it. We use a copy so we don't pollute the global registry.
    manager._specs["embeddings"] = ModelSpec(
        name="embeddings",
        url=spec.url,
        checksum=digest,
        description=spec.description,
        size=len(payload),
    )
    (models_dir / "embeddings.bin").write_bytes(payload)

    status = manager.check_models()
    assert status["embeddings"] is True
    assert status["stt"] is False
    assert status["tts"] is False


def test_download_progress_reports_correct_bytes(
    manager: ModelManager, models_dir: Path
) -> None:
    """download_model() updates progress to reflect bytes downloaded / total."""
    payload = b"x" * 4096
    digest = _sha256(payload)

    def handler(request: httpx.Request) -> httpx.Response:
        # No Range request — fresh download.
        return httpx.Response(200, content=payload, headers={"Content-Length": str(len(payload))})

    client = _make_client(handler)
    manager._specs["stt"] = ModelSpec(
        name="stt",
        url="https://example.com/stt.bin",
        checksum=digest,
        description="STT model",
        size=len(payload),
    )

    async def run() -> None:
        await manager.download_model("stt", client=client)

    asyncio.run(run())

    progress = manager.get_download_progress()
    assert progress["stt"].downloaded == len(payload)
    assert progress["stt"].total == len(payload)
    assert progress["stt"].status == "completed"
    # File should exist at the final path with correct contents.
    assert (models_dir / "stt.bin").read_bytes() == payload
    # .part file should be cleaned up.
    assert not (models_dir / "stt.bin.part").exists()


def test_checksum_verify_validates_sha256(
    manager: ModelManager, models_dir: Path
) -> None:
    """A correct checksum passes; a mismatched checksum raises and marks failed."""
    payload = b"the quick brown fox jumps over the lazy dog"
    good_digest = _sha256(payload)
    bad_digest = "0" * 64

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload, headers={"Content-Length": str(len(payload))})

    # --- Good checksum ---
    client_good = _make_client(handler)
    manager._specs["tts"] = ModelSpec(
        name="tts",
        url="https://example.com/tts.bin",
        checksum=good_digest,
        description="TTS model",
        size=len(payload),
    )

    async def run_good() -> None:
        await manager.download_model("tts", client=client_good)

    asyncio.run(run_good())
    assert manager.get_download_progress()["tts"].status == "completed"
    assert (models_dir / "tts.bin").exists()

    # --- Bad checksum ---
    client_bad = _make_client(handler)
    manager._specs["stt"] = ModelSpec(
        name="stt",
        url="https://example.com/stt.bin",
        checksum=bad_digest,
        description="STT model",
        size=len(payload),
    )

    async def run_bad() -> None:
        with pytest.raises(ValueError, match="checksum"):
            await manager.download_model("stt", client=client_bad)

    asyncio.run(run_bad())
    progress = manager.get_download_progress()["stt"]
    assert progress.status == "failed"
    assert "checksum" in (progress.error or "").lower()
    # Failed download should not leave a "completed" final file.
    assert not (models_dir / "stt.bin").exists()


def test_resume_download_from_partial_file(
    manager: ModelManager, models_dir: Path
) -> None:
    """A partial .part file triggers a Range request and the download completes."""
    full_payload = bytes(range(256)) * 64  # 16 KiB
    digest = _sha256(full_payload)
    part_size = len(full_payload) // 2
    part_payload = full_payload[:part_size]

    # Pre-seed the .part file with the first half.
    (models_dir / "embeddings.bin.part").write_bytes(part_payload)

    def handler(request: httpx.Request) -> httpx.Response:
        range_header = request.headers.get("Range")
        if range_header is None:
            # Should not happen — we have a .part file so a Range is expected.
            return httpx.Response(200, content=full_payload)
        # Parse "bytes=START-END" or "bytes=START-"
        assert range_header.startswith("bytes=")
        start_str = range_header[len("bytes="):].split("-")[0]
        start = int(start_str)
        assert start == part_size, f"Expected resume at {part_size}, got {start}"
        chunk = full_payload[start:]
        return httpx.Response(
            206,
            content=chunk,
            headers={
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{len(full_payload) - 1}/{len(full_payload)}",
            },
        )

    client = _make_client(handler)
    manager._specs["embeddings"] = ModelSpec(
        name="embeddings",
        url="https://example.com/embeddings.bin",
        checksum=digest,
        description="Embeddings model",
        size=len(full_payload),
    )

    async def run() -> None:
        await manager.download_model("embeddings", client=client)

    asyncio.run(run())

    progress = manager.get_download_progress()["embeddings"]
    assert progress.status == "completed"
    assert progress.downloaded == len(full_payload)
    assert (models_dir / "embeddings.bin").read_bytes() == full_payload
    assert not (models_dir / "embeddings.bin.part").exists()
