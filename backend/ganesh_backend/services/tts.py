"""Text-to-Speech (TTS) service layer.

Local speech synthesis via Piper (ONNX-runtime neural TTS) with a cloud
fallback to the ElevenLabs HTTP API when the local voice is unavailable or
synthesis fails.

``piper`` is imported lazily so this module loads in environments where
``piper-tts`` is not installed. The loaded ``PiperVoice`` is cached per
instance to avoid re-loading the ONNX model on every request. ElevenLabs
fallback uses ``httpx`` and resolves its API key from the shared keyring
store (``elevenlabs_api_key``) with an ``ELEVENLABS_API_KEY`` env fallback.
No model downloads happen at import time.
"""
from __future__ import annotations

import io
import os
import wave
from typing import Any, Optional

import httpx

from ganesh_backend.services.config import config_service

DEFAULT_PIPER_VOICE: str = ""

ELEVENLABS_API_BASE: str = "https://api.elevenlabs.io/v1"
ELEVENLABS_DEFAULT_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_DEFAULT_MODEL: str = "eleven_multilingual_v2"
ELEVENLABS_KEYRING_KEY: str = "elevenlabs_api_key"

LOCAL_AUDIO_FORMAT: str = "wav"
CLOUD_AUDIO_FORMAT: str = "mp3"


class TTSError(RuntimeError):
    """Raised when both local and cloud TTS fail."""


class TTSService:
    """TTS service: Piper local synthesis with ElevenLabs cloud fallback.

    Safe to instantiate even when ``piper-tts`` is not installed — the
    import is deferred until a voice model is actually requested.
    """

    def __init__(
        self,
        piper_voice_path: Optional[str] = None,
        elevenlabs_voice_id: Optional[str] = None,
        elevenlabs_api_key: Optional[str] = None,
        elevenlabs_model: Optional[str] = None,
    ) -> None:
        self._piper_voice_path: str = (
            piper_voice_path
            or os.environ.get("GANESH_TTS_VOICE", "")
            or config_service.get_setting("voice.piper_model", "")
            or DEFAULT_PIPER_VOICE
        )
        self._elevenlabs_voice_id: str = (
            elevenlabs_voice_id
            or os.environ.get("ELEVENLABS_VOICE_ID", "")
            or ELEVENLABS_DEFAULT_VOICE_ID
        )
        self._elevenlabs_model: str = (
            elevenlabs_model or ELEVENLABS_DEFAULT_MODEL
        )
        self._elevenlabs_api_key_override: Optional[str] = elevenlabs_api_key
        self._voice_cache: dict[str, Any] = {}

    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
    ) -> tuple[bytes, str, str]:
        """Synthesize ``text`` to audio.

        Returns ``(audio_bytes, content_type, source)`` where ``source`` is
        ``"local"`` or ``"cloud"``. Raises :class:`TTSError` when both
        backends fail and :class:`ValueError` when ``text`` is empty.
        """
        if not text or not text.strip():
            raise ValueError("text must be a non-empty string")

        local_audio = self._try_local(text, voice)
        if local_audio is not None:
            return local_audio, _content_type(LOCAL_AUDIO_FORMAT), "local"

        cloud_audio = self._try_cloud(text, voice)
        if cloud_audio is not None:
            return cloud_audio, _content_type(CLOUD_AUDIO_FORMAT), "cloud"

        raise TTSError("Both local and cloud TTS failed; no audio produced.")

    def is_available(self) -> bool:
        """Return whether any TTS backend is available."""
        return self._local_available() or self._cloud_available()

    def list_voices(self) -> list[dict[str, str]]:
        """Return available voices (local default + configured cloud voice)."""
        voices: list[dict[str, str]] = []
        if self._local_available():
            voices.append(
                {
                    "id": self._piper_voice_path or "piper-default",
                    "name": "Piper (local)",
                    "backend": "local",
                }
            )
        if self._cloud_available():
            voices.append(
                {
                    "id": self._elevenlabs_voice_id,
                    "name": "ElevenLabs (cloud)",
                    "backend": "cloud",
                }
            )
        return voices

    def _local_available(self) -> bool:
        if not self._piper_voice_path:
            return False
        return self._piper_importable()

    def _piper_importable(self) -> bool:
        try:
            import piper  # noqa: F401
        except ImportError:
            return False
        return True

    def _try_local(self, text: str, voice: Optional[str]) -> Optional[bytes]:
        model_path = voice or self._piper_voice_path
        if not model_path or not self._piper_importable():
            return None
        try:
            piper_voice = self._load_piper_voice(model_path)
            return self._render_piper_wav(piper_voice, text)
        except Exception:
            return None

    def _load_piper_voice(self, model_path: str) -> Any:
        cached = self._voice_cache.get(model_path)
        if cached is not None:
            return cached
        import piper

        voice = piper.PiperVoice.load(model_path)
        self._voice_cache[model_path] = voice
        return voice

    def _render_piper_wav(self, piper_voice: Any, text: str) -> bytes:
        cfg = getattr(piper_voice, "config", None)
        sample_rate = getattr(cfg, "sample_rate", 22050) if cfg else 22050

        import numpy as np

        pcm_chunks: list[bytes] = []
        for chunk in piper_voice.synthesize(text):
            audio = getattr(chunk, "audio_int16_array", None)
            if audio is None and isinstance(chunk, tuple):
                audio = chunk[0]
            pcm_chunks.append(np.asarray(audio, dtype=np.int16).tobytes())

        pcm = b"".join(pcm_chunks)
        return _wav_bytes(pcm, sample_rate)

    def _cloud_available(self) -> bool:
        return bool(self._resolve_elevenlabs_api_key())

    def _resolve_elevenlabs_api_key(self) -> Optional[str]:
        if self._elevenlabs_api_key_override is not None:
            return self._elevenlabs_api_key_override
        try:
            import keyring

            key = keyring.get_password("ganesh", ELEVENLABS_KEYRING_KEY)
        except Exception:
            key = None
        if not key:
            key = os.environ.get("ELEVENLABS_API_KEY")
        return key

    def _try_cloud(self, text: str, voice: Optional[str]) -> Optional[bytes]:
        api_key = self._resolve_elevenlabs_api_key()
        if not api_key:
            return None
        voice_id = voice or self._elevenlabs_voice_id
        url = f"{ELEVENLABS_API_BASE}/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {"text": text, "model_id": self._elevenlabs_model}
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, headers=headers, json=payload)
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        return resp.content


def _content_type(fmt: str) -> str:
    if fmt == "wav":
        return "audio/wav"
    if fmt == "mp3":
        return "audio/mpeg"
    return "application/octet-stream"


def _wav_bytes(
    pcm: bytes,
    sample_rate: int,
    num_channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(num_channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buf.getvalue()


_tts_service: Optional[TTSService] = None


def get_tts_service() -> TTSService:
    """Return the process-wide TTS service singleton."""
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
    return _tts_service


def reset_tts_service() -> None:
    """Clear the singleton (used by tests)."""
    global _tts_service
    _tts_service = None
