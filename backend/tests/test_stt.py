"""Tests for the /api/voice STT endpoints.

faster-whisper and Deepgram are mocked throughout — no model loads, no network.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

import main as main_module
from ganesh_backend.services import stt as stt_service


@pytest.fixture(autouse=True)
def _reset_caches():
    stt_service.reset_model_cache()
    stt_service.reset_deepgram_key_cache()
    yield
    stt_service.reset_model_cache()
    stt_service.reset_deepgram_key_cache()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(main_module.create_app())


def _fake_segment(text: str, avg_logprob: float = -0.3):
    return SimpleNamespace(text=text, avg_logprob=avg_logprob)


def _fake_model(segments, info):
    """A fake faster-whisper model whose .transcribe() returns (segs, info)."""
    return SimpleNamespace(
        transcribe=lambda path, language=None: (iter(segments), info)
    )


def test_transcribe_mock(client: TestClient, tmp_path) -> None:
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF....fake-audio....")

    fake_segments = [
        _fake_segment("hello", -0.2),
        _fake_segment(" world", -0.4),
    ]
    fake_info = SimpleNamespace(language="en", language_probability=0.99)
    fake_model = _fake_model(fake_segments, fake_info)

    with patch(
        "ganesh_backend.services.stt._load_local_model",
        return_value=fake_model,
    ), patch(
        "ganesh_backend.services.stt.get_deepgram_key",
        return_value="not-used",
    ):
        with client:
            response = client.post(
                "/api/voice/transcribe",
                files={"file": ("clip.wav", audio.read_bytes(), "audio/wav")},
            )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == "hello world"
    assert body["engine"] == "local"
    assert 0.0 <= body["confidence"] <= 1.0
    # exp(-0.3) ≈ 0.74 — sanity check the squashing math.
    assert body["confidence"] > 0.5


def test_stt_status(client: TestClient) -> None:
    with patch(
        "ganesh_backend.services.stt.is_local_available", return_value=True
    ), patch(
        "ganesh_backend.services.stt.is_model_loaded", return_value=False
    ), patch(
        "ganesh_backend.services.stt.get_deepgram_key", return_value="fake-key"
    ):
        with client:
            response = client.get("/api/voice/stt-status")

    assert response.status_code == 200
    body = response.json()
    assert body["local_available"] is True
    assert body["model_loaded"] is False
    assert body["cloud_available"] is True


def test_transcribe_no_audio(client: TestClient) -> None:
    with client:
        response = client.post("/api/voice/transcribe", files={})
    assert response.status_code == 400
    assert "no audio file" in response.json()["detail"]


def test_cloud_fallback(client: TestClient, tmp_path) -> None:
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"RIFF....fake-audio....")

    deepgram_payload = {
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": "cloud says hi",
                            "confidence": 0.95,
                        }
                    ]
                }
            ]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/listen"
        assert request.headers["authorization"] == "Token test-deepgram-key"
        return httpx.Response(200, json=deepgram_payload)

    mock_transport = httpx.MockTransport(handler)

    # Patch httpx.AsyncClient inside the stt module so the one-shot client
    # created by transcribe_cloud_async uses our MockTransport — no real
    # network call is made.
    real_async_client = httpx.AsyncClient

    def fake_async_client(*args, **kwargs):
        kwargs["transport"] = mock_transport
        return real_async_client(*args, **kwargs)

    with patch(
        "ganesh_backend.services.stt.transcribe_local",
        side_effect=stt_service.STTUnavailableError("local unavailable"),
    ), patch(
        "ganesh_backend.services.stt.get_deepgram_key",
        return_value="test-deepgram-key",
    ), patch(
        "ganesh_backend.services.stt.httpx.AsyncClient",
        side_effect=fake_async_client,
    ):
        with client:
            response = client.post(
                "/api/voice/transcribe",
                files={"file": ("clip.wav", audio.read_bytes(), "audio/wav")},
            )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == "cloud says hi"
    assert body["engine"] == "cloud"
    assert body["confidence"] == pytest.approx(0.95)
