"""Tests for the TTS service and /api/voice TTS endpoints.

Piper and ElevenLabs are mocked throughout — no real model loads or network
calls are made.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

import main as main_module
from ganesh_backend.services.tts import TTSService, reset_tts_service


@pytest.fixture(autouse=True)
def _reset_tts_singleton():
    reset_tts_service()
    yield
    reset_tts_service()


def _fake_audio_chunk() -> SimpleNamespace:
    return SimpleNamespace(
        audio_int16_array=np.array([0, 1024, -1024, 32767, -32768], dtype=np.int16),
        sample_rate=22050,
    )


def _make_service_with_local() -> TTSService:
    return TTSService(piper_voice_path="/fake/voice.onnx")


def _patch_piper_voice():
    fake_voice = SimpleNamespace(
        config=SimpleNamespace(sample_rate=22050),
        synthesize=lambda text: iter([_fake_audio_chunk()]),
    )
    return patch(
        "piper.PiperVoice.load",
        return_value=fake_voice,
    )


def test_synthesize_mock():
    service = _make_service_with_local()
    with _patch_piper_voice():
        audio_bytes, content_type, source = service.synthesize("hello world")

    assert source == "local"
    assert content_type == "audio/wav"
    assert isinstance(audio_bytes, (bytes, bytearray))
    assert len(audio_bytes) > 0
    assert audio_bytes[:4] == b"RIFF"
    assert audio_bytes[8:12] == b"WAVE"


def test_tts_status():
    local_service = TTSService(
        piper_voice_path="/fake/voice.onnx",
        elevenlabs_api_key=None,
    )
    with patch.object(local_service, "_local_available", return_value=True), \
         patch.object(local_service, "_cloud_available", return_value=False):
        with patch(
            "ganesh_backend.routers.voice.get_tts_service",
            return_value=local_service,
        ):
            client = TestClient(main_module.create_app())
            with client:
                resp = client.get("/api/voice/tts-status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["local"] is True
    assert body["cloud"] is False


def test_synthesize_no_text():
    client = TestClient(main_module.create_app())
    with client:
        resp = client.post("/api/voice/synthesize", json={"text": ""})
    assert resp.status_code == 400
    assert "non-empty" in resp.json()["detail"]

    with client:
        resp = client.post("/api/voice/synthesize", json={"text": "   "})
    assert resp.status_code == 400


def test_cloud_fallback():
    service = TTSService(
        piper_voice_path="/missing/voice.onnx",
        elevenlabs_api_key="fake-key",
    )
    fake_response = SimpleNamespace(status_code=200, content=b"\x00\x01\x02MP3")
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = fake_response
    with patch("ganesh_backend.services.tts.httpx.Client", return_value=mock_client):
        audio_bytes, content_type, source = service.synthesize("hello")

    assert source == "cloud"
    assert content_type == "audio/mpeg"
    assert audio_bytes == b"\x00\x01\x02MP3"
    mock_client.post.assert_called_once()
