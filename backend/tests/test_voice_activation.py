"""Tests for the voice activation service and /api/voice activation endpoints.

sherpa-onnx wake-word / VAD detectors are mocked throughout — no model
downloads, no real audio processing.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

import main as main_module  # noqa: E402
from ganesh_backend.routers.voice import (  # noqa: E402
    reset_voice_activation_service,
    set_voice_activation_service,
)
from ganesh_backend.services.voice_activation import (  # noqa: E402
    ActivationMode,
    IllegalTransitionError,
    VoiceActivationService,
    VoiceState,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_voice_activation_service()
    yield
    reset_voice_activation_service()


def _make_service(
    mode: ActivationMode = ActivationMode.PUSH_TO_TALK,
    wake_word_detector=None,
    vad_detector=None,
    tts_canceller=None,
    llm_canceller=None,
) -> VoiceActivationService:
    return VoiceActivationService(
        mode=mode,
        wake_word_detector=wake_word_detector,
        vad_detector=vad_detector,
        tts_canceller=tts_canceller,
        llm_canceller=llm_canceller,
    )


def _wire(service: VoiceActivationService) -> TestClient:
    set_voice_activation_service(service)
    client = TestClient(main_module.create_app())
    return client


# ---------------------------------------------------------------------------
# 1. push-to-talk
# ---------------------------------------------------------------------------


def test_push_to_talk():
    service = _make_service(mode=ActivationMode.PUSH_TO_TALK)
    client = _wire(service)

    assert service.get_state() == VoiceState.IDLE

    # button down
    r = client.post("/api/voice/start-listening")
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "listening"
    assert service.get_state() == VoiceState.LISTENING

    # stream a couple of audio chunks (push-to-talk buffers them)
    r1 = client.post("/api/voice/audio-chunk", json={"chunk": "AAEC"})
    assert r1.status_code == 200
    assert r1.json()["state"] == "listening"
    r2 = client.post("/api/voice/audio-chunk", json={"chunk": "AAEC"})
    assert r2.status_code == 200

    # button up — stops recording, transitions to PROCESSING
    r = client.post("/api/voice/stop-listening")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "processing"
    assert body["audio_size"] > 0
    assert service.get_state() == VoiceState.PROCESSING

    # orchestrator signals TTS start/finish
    service.on_speaking_started()
    assert service.get_state() == VoiceState.SPEAKING
    service.on_speaking_finished()
    assert service.get_state() == VoiceState.IDLE

    # cannot stop_listening from IDLE
    with pytest.raises(IllegalTransitionError):
        service.stop_listening()


# ---------------------------------------------------------------------------
# 2. wake word
# ---------------------------------------------------------------------------


def test_wake_word():
    wake_detector = MagicMock()
    wake_detector.is_wake_word_detected = MagicMock(
        side_effect=lambda audio: b"WAKE" in audio
    )
    service = _make_service(
        mode=ActivationMode.WAKE_WORD,
        wake_word_detector=wake_detector,
    )
    client = _wire(service)

    assert service.get_state() == VoiceState.IDLE

    # silent chunk — no transition
    r = client.post("/api/voice/audio-chunk", json={"chunk": "AAAA"})
    assert r.status_code == 200
    assert r.json()["state"] == "idle"
    assert service.get_state() == VoiceState.IDLE

    # wake-word chunk — transitions to LISTENING
    r = client.post("/api/voice/audio-chunk", json={"chunk": "AAEC"})
    # base64 "AAEC" decodes to bytes containing 0x00 0x01 0x02 — not "WAKE".
    # Use a raw-bytes path: call the service directly to inject a real wake word.
    _ = r
    new_state = service.process_audio_chunk(b"WAKE-word-audio")
    assert new_state == VoiceState.LISTENING
    assert service.get_state() == VoiceState.LISTENING
    wake_detector.is_wake_word_detected.assert_called()

    # subsequent chunks accumulate while listening
    service.process_audio_chunk(b"more-audio")
    captured = service.stop_listening()
    assert b"WAKE-word-audio" in captured
    assert b"more-audio" in captured
    assert service.get_state() == VoiceState.PROCESSING

    # is_wake_word_detected public hook
    assert service.is_wake_word_detected(b"WAKE") is True
    assert service.is_wake_word_detected(b"silence") is False


# ---------------------------------------------------------------------------
# 3. VAD
# ---------------------------------------------------------------------------


def test_vad():
    vad = MagicMock()
    vad.is_voice_activity_detected = MagicMock(
        side_effect=lambda audio: b"VOICE" in audio
    )
    service = _make_service(
        mode=ActivationMode.VAD_ALWAYS_ON,
        vad_detector=vad,
    )
    client = _wire(service)

    assert service.get_state() == VoiceState.IDLE

    # silence — no transition
    r = client.post("/api/voice/audio-chunk", json={"chunk": "AAAA"})
    assert r.status_code == 200
    assert r.json()["state"] == "idle"

    # voice detected — auto-trigger LISTENING
    new_state = service.process_audio_chunk(b"VOICE-audio")
    assert new_state == VoiceState.LISTENING
    assert service.get_state() == VoiceState.LISTENING
    vad.is_voice_activity_detected.assert_called()

    # is_voice_activity_detected public hook
    assert service.is_voice_activity_detected(b"VOICE") is True
    assert service.is_voice_activity_detected(b"silence") is False

    # finish the listening cycle
    service.stop_listening()
    assert service.get_state() == VoiceState.PROCESSING


# ---------------------------------------------------------------------------
# 4. barge-in
# ---------------------------------------------------------------------------


def test_barge_in():
    tts_cancelled = []
    llm_cancelled = []
    vad = MagicMock()
    vad.is_voice_activity_detected = MagicMock(
        side_effect=lambda audio: b"VOICE" in audio
    )
    service = _make_service(
        mode=ActivationMode.VAD_ALWAYS_ON,
        vad_detector=vad,
        tts_canceller=lambda: tts_cancelled.append(True),
        llm_canceller=lambda: llm_cancelled.append(True),
    )
    client = _wire(service)

    # drive the machine into SPEAKING
    service.process_audio_chunk(b"VOICE")
    assert service.get_state() == VoiceState.LISTENING
    service.stop_listening()
    assert service.get_state() == VoiceState.PROCESSING
    service.on_speaking_started()
    assert service.get_state() == VoiceState.SPEAKING

    # barge-in via HTTP
    r = client.post("/api/voice/barge-in")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "listening"
    assert body["cancelled_tts"] is True
    assert body["cancelled_llm"] is True

    assert service.get_state() == VoiceState.LISTENING
    assert tts_cancelled == [True]
    assert llm_cancelled == [True]

    # barge-in from a non-SPEAKING state is illegal
    with pytest.raises(IllegalTransitionError):
        service.barge_in()

    # barge-in via VAD while speaking: drive back to SPEAKING then send voice
    service.stop_listening()
    service.on_speaking_started()
    assert service.get_state() == VoiceState.SPEAKING
    new_state = service.process_audio_chunk(b"VOICE-barge")
    assert new_state == VoiceState.LISTENING
    assert tts_cancelled == [True, True]
    assert llm_cancelled == [True, True]
