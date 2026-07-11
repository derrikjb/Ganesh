"""Tests for the TTS service and /api/voice TTS endpoints.

Kokoro (local) and ElevenLabs (cloud) are mocked throughout — no real model
loads or network calls are made.
"""
from __future__ import annotations

import io
import os
import struct
import sys
import types
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

import main as main_module  # noqa: E402
from ganesh_backend.services import stt as stt_service  # noqa: E402
from ganesh_backend.services.config import config_service  # noqa: E402
from ganesh_backend.services.tts import (  # noqa: E402
    DEFAULT_KOKORO_VOICE,
    TTSError,
    TTSService,
    reset_tts_service,
    strip_markdown,
)

KOKORO_VOICE_NAMES = ["af_heart", "af_bella", "am_adam"]


@pytest.fixture(autouse=True)
def _reset_tts_singleton():
    reset_tts_service()
    config_service.set_setting("voice.tts_voice_name", DEFAULT_KOKORO_VOICE)
    config_service.set_setting("voice.tts_engine", "local")
    with patch("ganesh_backend.services.config.config_service.get_voice_provider_key", return_value=None), \
         patch("ganesh_backend.services.config.config_service.get_voice_provider_key_env", return_value=None):
        yield
    reset_tts_service()
    config_service.set_setting("voice.tts_voice_name", DEFAULT_KOKORO_VOICE)


def _make_fake_soundfile() -> types.ModuleType:
    """Build a fake ``soundfile`` module whose ``write`` emits real WAV bytes.

    Kokoro's ``_render_kokoro_wav`` does ``import soundfile as sf`` lazily, so
    we inject this stub into ``sys.modules`` to avoid requiring the real
    (optional) soundfile package in the test environment.
    """

    fake_sf = types.ModuleType("soundfile")

    def _write(buf, samples, sample_rate, format=None, subtype=None) -> None:
        if hasattr(samples, "tolist"):
            samples = samples.tolist()
        pcm = struct.pack(
            f"<{len(samples)}h",
            *[max(-32768, min(32767, int(s * 32767))) for s in samples],
        )
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm)

    fake_sf.write = _write
    return fake_sf


def _make_mock_kokoro() -> MagicMock:
    mock = MagicMock()
    mock.create.return_value = (np.zeros(1000, dtype=np.float32), 24000)
    mock.get_voices.return_value = list(KOKORO_VOICE_NAMES)
    return mock


def _make_service_with_local() -> TTSService:
    return TTSService(elevenlabs_api_key=None)


def test_synthesize_mock():
    service = _make_service_with_local()
    mock_kokoro = _make_mock_kokoro()

    with patch.object(TTSService, "_kokoro_importable", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch.object(service, "_load_kokoro", return_value=mock_kokoro), \
         patch.dict(sys.modules, {"soundfile": _make_fake_soundfile()}):
        audio_bytes, content_type, source = service.synthesize("hello world")

    assert source == "local"
    assert content_type == "audio/wav"
    assert isinstance(audio_bytes, (bytes, bytearray))
    assert len(audio_bytes) > 0
    assert audio_bytes[:4] == b"RIFF"
    assert audio_bytes[8:12] == b"WAVE"
    mock_kokoro.create.assert_called_once_with(
        "hello world", voice="af_heart", speed=1.0, lang="en-us"
    )


def test_tts_status():
    service = TTSService(elevenlabs_api_key=None)
    with patch.object(TTSService, "_kokoro_importable", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch.object(service, "_cloud_available", return_value=False), \
         patch("ganesh_backend.routers.voice.get_tts_service", return_value=service):
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
    service = TTSService(elevenlabs_api_key="fake-key")
    fake_response = SimpleNamespace(status_code=200, content=b"\x00\x01\x02MP3")
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = fake_response
    with patch("ganesh_backend.services.tts.httpx.Client", return_value=mock_client), \
         patch.object(service, "_try_local", return_value=None):
        audio_bytes, content_type, source = service.synthesize("hello")

    assert source == "cloud"
    assert content_type == "audio/mpeg"
    assert audio_bytes == b"\x00\x01\x02MP3"
    mock_client.post.assert_called_once()


def test_chime_default():
    client = TestClient(main_module.create_app())
    with client:
        resp = client.post("/api/voice/chime", json={})

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    body = resp.content
    assert len(body) > 0
    assert body[:4] == b"RIFF"
    assert body[8:12] == b"WAVE"


def test_chime_volume():
    client = TestClient(main_module.create_app())
    with client:
        resp = client.post("/api/voice/chime", json={"volume": 0.0})

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    body = resp.content
    assert body[:4] == b"RIFF"
    assert body[8:12] == b"WAVE"

    buf = io.BytesIO(body)
    with wave.open(buf, "rb") as wav:
        frames = wav.readframes(wav.getnframes())
    num_samples = len(frames) // 2
    samples = struct.unpack(f"<{num_samples}h", frames)
    assert all(s == 0 for s in samples)


def test_chime_invalid_volume():
    client = TestClient(main_module.create_app())
    with client:
        resp = client.post("/api/voice/chime", json={"volume": 1.5})

    assert resp.status_code == 422


def test_kokoro_voice_list():
    service = TTSService(elevenlabs_api_key=None)
    mock_voices = [
        {"id": "af_heart", "name": "af_heart", "backend": "local"},
        {"id": "af_bella", "name": "af_bella", "backend": "local"},
        {"id": "am_adam", "name": "am_adam", "backend": "local"},
        {"id": "21m00Tcm4TlvDq8ikWAM", "name": "ElevenLabs (cloud)", "backend": "cloud"},
    ]
    with patch("ganesh_backend.routers.voice.get_tts_service", return_value=service), \
         patch.object(service, "list_voices", return_value=mock_voices):
        client = TestClient(main_module.create_app())
        with client:
            resp = client.get("/api/voice/tts-voices")

    assert resp.status_code == 200
    body = resp.json()
    voices = body["voices"]
    assert "af_heart" in voices
    assert "af_bella" in voices
    assert "am_adam" in voices
    assert "21m00Tcm4TlvDq8ikWAM" not in voices


def test_kokoro_voice_change():
    service = TTSService(elevenlabs_api_key=None)
    service._kokoro_cache["preloaded"] = "stale_instance"
    assert len(service._kokoro_cache) == 1

    with patch("ganesh_backend.routers.voice.get_tts_service", return_value=service), \
         patch.object(service, "list_voices", return_value=[]), \
         patch.object(service, "_local_available", return_value=False), \
         patch.object(service, "_cloud_available", return_value=False), \
         patch.object(stt_service, "is_local_available", return_value=False), \
         patch.object(stt_service, "is_cuda_available", return_value=False), \
         patch.object(stt_service, "get_deepgram_key", side_effect=stt_service.STTError("no key")), \
         patch.object(config_service, "save_config"):
        client = TestClient(main_module.create_app())
        with client:
            resp = client.put(
                "/api/voice/settings", json={"tts_voice_name": "af_bella"}
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["tts_voice_name"] == "af_bella"
    assert config_service.get_setting("voice.tts_voice_name") == "af_bella"
    assert len(service._kokoro_cache) == 0


def test_kokoro_model_missing():
    service = TTSService(elevenlabs_api_key="fake-key")

    with patch.object(TTSService, "_kokoro_importable", return_value=True), \
         patch("os.path.isfile", return_value=False):
        assert service._local_available() is False

    fake_response = SimpleNamespace(status_code=200, content=b"\x00\x01\x02MP3")
    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.post.return_value = fake_response
    with patch.object(TTSService, "_kokoro_importable", return_value=True), \
         patch("os.path.isfile", return_value=False), \
         patch("ganesh_backend.services.tts.httpx.Client", return_value=mock_client):
        audio_bytes, content_type, source = service.synthesize("hello")

    assert source == "cloud"
    assert content_type == "audio/mpeg"
    assert audio_bytes == b"\x00\x01\x02MP3"

    service_no_cloud = TTSService(elevenlabs_api_key=None)
    with patch.object(TTSService, "_kokoro_importable", return_value=True), \
         patch("os.path.isfile", return_value=False):
        with pytest.raises(TTSError):
            service_no_cloud.synthesize("hello")


def test_strip_markdown_utility():
    assert strip_markdown("# Header") == "Header"
    assert strip_markdown("**bold** and _italic_") == "bold and italic"
    assert strip_markdown("`code` and ```block\ncontent\n```") == "code and block\ncontent"
    assert strip_markdown("[link](http://ex.com)") == "link"
    assert strip_markdown("![img](http://ex.com/i.png)") == "img"
    assert strip_markdown("- item 1\n* item 2\n1. item 3") == "item 1\nitem 2\nitem 3"
    assert strip_markdown("> quote") == "quote"
    assert strip_markdown("~~strike~~") == "strike"
    assert strip_markdown("---\n***\n___") == ""
    assert strip_markdown("| a | b |\n|---|---|\n| c | d |") == "a   b\nc   d"
    assert strip_markdown("<div>html</div>") == "html"


def test_synthesize_strips_markdown():
    service = _make_service_with_local()
    mock_kokoro = _make_mock_kokoro()

    with patch.object(TTSService, "_kokoro_importable", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch.object(service, "_load_kokoro", return_value=mock_kokoro), \
         patch.dict(sys.modules, {"soundfile": _make_fake_soundfile()}):
        service.synthesize("**bold** text")

    mock_kokoro.create.assert_called_once_with(
        "bold text", voice="af_heart", speed=1.0, lang="en-us"
    )


def test_synthesize_markdown_only_raises_error():
    service = _make_service_with_local()
    with pytest.raises(ValueError, match="non-empty"):
        service.synthesize("***")
