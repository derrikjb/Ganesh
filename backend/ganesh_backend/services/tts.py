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
import uuid
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
            or config_service.get_setting(
                "voice.elevenlabs_voice_id", ELEVENLABS_DEFAULT_VOICE_ID
            )
            or ELEVENLABS_DEFAULT_VOICE_ID
        )
        self._elevenlabs_model: str = (
            elevenlabs_model or ELEVENLABS_DEFAULT_MODEL
        )
        self._elevenlabs_api_key_override: Optional[str] = elevenlabs_api_key
        self._voice_cache: dict[str, Any] = {}

    def _piper_voices(self) -> list[dict[str, str]]:
        voices = config_service.get_setting("voice.piper_voices", [])
        if not isinstance(voices, list):
            return []
        return [v for v in voices if isinstance(v, dict)]

    def _active_piper_voice_path(self) -> Optional[str]:
        active_id = config_service.get_setting("voice.piper_active_voice")
        if not active_id:
            return None
        for v in self._piper_voices():
            if v.get("id") == active_id:
                return v.get("path") or None
        return None

    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
    ) -> tuple[bytes, str, str]:
        """Synthesize ``text`` to audio.

        Returns ``(audio_bytes, content_type, source)`` where ``source`` is
        ``"local"`` or ``"cloud"``. Raises :class:`TTSError` when both
        backends fail and :class:`ValueError` when ``text`` is empty.

        Engine order is controlled by ``voice.tts_engine`` config:
        ``"local"`` (default) tries local first; ``"cloud"`` tries cloud first.
        """
        if not text or not text.strip():
            raise ValueError("text must be a non-empty string")

        engine_pref = config_service.get_setting("voice.tts_engine", "local")
        if engine_pref == "cloud":
            cloud_audio = self._try_cloud(text, voice)
            if cloud_audio is not None:
                return cloud_audio, _content_type(CLOUD_AUDIO_FORMAT), "cloud"
            local_audio = self._try_local(text, voice)
            if local_audio is not None:
                return local_audio, _content_type(LOCAL_AUDIO_FORMAT), "local"
        else:
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
        """Return all configured Piper voices plus the ElevenLabs cloud voice."""
        voices: list[dict[str, str]] = []
        for v in self._piper_voices():
            path = v.get("path") or ""
            if path and self._piper_importable():
                voices.append(
                    {
                        "id": v.get("id", path),
                        "name": v.get("name", "Piper voice"),
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

    def set_active_voice(self, voice_id: str) -> None:
        """Set ``voice.piper_active_voice`` in config."""
        config_service.set_setting("voice.piper_active_voice", voice_id)

    def add_voice(self, name: str, path: str) -> dict[str, str]:
        """Append a new Piper voice to ``voice.piper_voices`` in config."""
        voice = {"id": str(uuid.uuid4()), "name": name, "path": path}
        voices = self._piper_voices()
        voices.append(voice)
        config_service.set_setting("voice.piper_voices", voices)
        return voice

    def remove_voice(self, voice_id: str) -> bool:
        """Remove a Piper voice by id; clears active if it was active."""
        voices = self._piper_voices()
        new_voices = [v for v in voices if v.get("id") != voice_id]
        removed = len(new_voices) != len(voices)
        if removed:
            config_service.set_setting("voice.piper_voices", new_voices)
            active = config_service.get_setting("voice.piper_active_voice")
            if active == voice_id:
                config_service.set_setting("voice.piper_active_voice", None)
        return removed

    def _local_available(self) -> bool:
        path = self._active_piper_voice_path() or self._piper_voice_path
        if not path:
            return False
        return self._piper_importable()

    def _piper_importable(self) -> bool:
        try:
            import piper  # noqa: F401
        except Exception:
            return False
        return True

    def _try_local(self, text: str, voice: Optional[str]) -> Optional[bytes]:
        model_path = voice or self._active_piper_voice_path() or self._piper_voice_path
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

        use_cuda = self._resolve_use_cuda()
        voice = piper.PiperVoice.load(model_path, use_cuda=use_cuda)
        self._voice_cache[model_path] = voice
        return voice

    @staticmethod
    def _resolve_use_cuda() -> bool:
        preference = config_service.get_setting("voice.tts_device", "auto")
        if preference == "cpu":
            return False
        if preference == "cuda":
            return True
        # auto: use CUDA if onnxruntime has the CUDA execution provider
        try:
            import onnxruntime
            return "CUDAExecutionProvider" in onnxruntime.get_available_providers()
        except Exception:
            return False

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
        key = config_service.get_voice_provider_key("elevenlabs")
        if not key:
            key = config_service.get_voice_provider_key_env("elevenlabs")
        if not key:
            # Legacy keyring account fallback for existing installs.
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
