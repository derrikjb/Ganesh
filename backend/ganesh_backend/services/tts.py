"""Text-to-Speech (TTS) service layer.

Local speech synthesis via Kokoro (ONNX-runtime neural TTS) with a cloud
fallback to the ElevenLabs HTTP API when the local voice is unavailable or
synthesis fails.

``kokoro_onnx`` is imported lazily so this module loads in environments where
``kokoro-onnx`` is not installed. The loaded ``Kokoro`` instance is cached per
instance to avoid re-loading the ONNX model on every request. ElevenLabs
fallback uses ``httpx`` and resolves its API key from the shared keyring
store (``elevenlabs_api_key``) with an ``ELEVENLABS_API_KEY`` env fallback.
No model downloads happen at import time.
"""
from __future__ import annotations

import io
import logging
import os
import re
import wave
from pathlib import Path
from typing import Any, Optional

import httpx

from ganesh_backend.services.config import config_service

logger = logging.getLogger(__name__)

DEFAULT_KOKORO_VOICE: str = "af_heart"
DEFAULT_MODEL_FILENAME: str = "kokoro-v1.0.onnx"
DEFAULT_VOICES_FILENAME: str = "voices-v1.0.bin"

ELEVENLABS_API_BASE: str = "https://api.elevenlabs.io/v1"
ELEVENLABS_DEFAULT_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"
ELEVENLABS_DEFAULT_MODEL: str = "eleven_multilingual_v2"
ELEVENLABS_KEYRING_KEY: str = "elevenlabs_api_key"

LOCAL_AUDIO_FORMAT: str = "wav"
CLOUD_AUDIO_FORMAT: str = "mp3"


def strip_markdown(text: str) -> str:
    """Remove markdown formatting from text for speech synthesis."""
    text = re.sub(r"<[^>]*>", "", text)
    text = re.sub(r"!\[(.*?)\]\(.*?\)", r"\1", text)
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    text = re.sub(r"```+(.*?)```+", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"`(.*?)`", r"\1", text)

    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            lines.append("")
            continue

        if re.match(r"^([-*_]){3,}$", line):
            continue

        line = re.sub(r"^#+\s+", "", line)
        line = re.sub(r"^([-*+]\s+|\d+\.\s+)", "", line)
        line = re.sub(r"^>\s+", "", line)

        if "|" in line:
            if re.match(r"^\|?[:\s-]*(\|[:\s-]*)*\|?$", line):
                continue
            line = line.replace("|", " ").strip()

        lines.append(line)

    text = "\n".join(lines)
    text = re.sub(r"(\*\*|__|~~)(.*?)\1", r"\2", text)
    text = re.sub(r"(\*|_)(.*?)\1", r"\2", text)
    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text.strip()


class TTSError(RuntimeError):
    """Raised when both local and cloud TTS fail."""


class TTSService:
    """TTS service: Kokoro local synthesis with ElevenLabs cloud fallback.

    Safe to instantiate even when ``kokoro-onnx`` is not installed — the
    import is deferred until a voice is actually requested.
    """

    def __init__(
        self,
        elevenlabs_voice_id: Optional[str] = None,
        elevenlabs_api_key: Optional[str] = None,
        elevenlabs_model: Optional[str] = None,
    ) -> None:
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
        self._kokoro_cache: dict[str, Any] = {}

    @staticmethod
    def _default_models_dir() -> Path:
        return Path.home() / ".ganesh" / "models"

    def _model_path(self) -> str:
        configured = config_service.get_setting("voice.tts_model_path", "")
        if configured:
            return str(configured)
        return str(self._default_models_dir() / DEFAULT_MODEL_FILENAME)

    def _voices_path(self) -> str:
        configured = config_service.get_setting("voice.tts_voices_path", "")
        if configured:
            return str(configured)
        return str(self._default_models_dir() / DEFAULT_VOICES_FILENAME)

    def get_active_voice(self) -> str:
        """Return the configured active Kokoro voice name (default ``af_heart``)."""
        name = config_service.get_setting("voice.tts_voice_name", "")
        if not name:
            return DEFAULT_KOKORO_VOICE
        return str(name)

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
        text = strip_markdown(text)
        if not text or not text.strip():
            raise ValueError("text must be a non-empty string")

        engine_pref = config_service.get_setting("voice.tts_engine", "local")
        if engine_pref == "cloud":
            cloud_audio = self._try_cloud(text, voice)
            if cloud_audio is not None:
                logger.info("TTS synthesis: engine=%s, source=%s", engine_pref, "cloud")
                return cloud_audio, _content_type(CLOUD_AUDIO_FORMAT), "cloud"
            local_audio = self._try_local(text, voice)
            if local_audio is not None:
                logger.info("TTS synthesis: engine=%s, source=%s", engine_pref, "local")
                return local_audio, _content_type(LOCAL_AUDIO_FORMAT), "local"
        else:
            local_audio = self._try_local(text, voice)
            if local_audio is not None:
                logger.info("TTS synthesis: engine=%s, source=%s", engine_pref, "local")
                return local_audio, _content_type(LOCAL_AUDIO_FORMAT), "local"
            cloud_audio = self._try_cloud(text, voice)
            if cloud_audio is not None:
                logger.info("TTS synthesis: engine=%s, source=%s", engine_pref, "cloud")
                return cloud_audio, _content_type(CLOUD_AUDIO_FORMAT), "cloud"

        logger.error("TTS synthesis failed: both local and cloud unavailable")
        raise TTSError("Both local and cloud TTS failed; no audio produced.")

    def is_available(self) -> bool:
        """Return whether any TTS backend is available."""
        return self._local_available() or self._cloud_available()

    def list_voices(self) -> list[dict[str, str]]:
        """Return available Kokoro voice names plus the ElevenLabs cloud voice."""
        voices: list[dict[str, str]] = []
        if self._kokoro_importable():
            try:
                kokoro = self._load_kokoro()
                for name in kokoro.get_voices():
                    voices.append(
                        {
                            "id": str(name),
                            "name": str(name),
                            "backend": "local",
                        }
                    )
            except Exception as exc:
                logger.warning("TTS list_voices: could not enumerate Kokoro voices: %s", exc)
        if self._cloud_available():
            voices.append(
                {
                    "id": self._elevenlabs_voice_id,
                    "name": "ElevenLabs (cloud)",
                    "backend": "cloud",
                }
            )
        return voices

    def set_active_voice(self, voice_name: str) -> None:
        """Set ``voice.tts_voice_name`` in config and clear the Kokoro cache."""
        config_service.set_setting("voice.tts_voice_name", voice_name)
        self._kokoro_cache.clear()

    def _local_available(self) -> bool:
        if not self._kokoro_importable():
            return False
        model_path = self._model_path()
        voices_path = self._voices_path()
        return os.path.isfile(model_path) and os.path.isfile(voices_path)

    @staticmethod
    def _kokoro_importable() -> bool:
        try:
            import kokoro_onnx  # noqa: F401
        except Exception:
            return False
        return True

    def _try_local(self, text: str, voice: Optional[str]) -> Optional[bytes]:
        if not self._kokoro_importable():
            logger.warning("TTS local synthesis skipped: kokoro_onnx not importable")
            return None
        model_path = self._model_path()
        voices_path = self._voices_path()
        if not os.path.isfile(model_path) or not os.path.isfile(voices_path):
            logger.warning(
                "TTS local synthesis skipped: model files missing "
                "(model=%s, voices=%s)",
                model_path,
                voices_path,
            )
            return None
        voice_name = voice or self.get_active_voice()
        try:
            kokoro = self._load_kokoro()
            return self._render_kokoro_wav(kokoro, text, voice_name)
        except Exception as exc:
            logger.exception("TTS local synthesis failed: %s", exc)
            return None

    def _load_kokoro(self) -> Any:
        model_path = self._model_path()
        cached = self._kokoro_cache.get(model_path)
        if cached is not None:
            return cached
        from kokoro_onnx import Kokoro

        use_cuda = self._resolve_use_cuda()
        if use_cuda:
            logger.info("TTS local: CUDA execution provider available")
        kokoro = Kokoro(model_path, self._voices_path())
        self._kokoro_cache[model_path] = kokoro
        return kokoro

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

    def _render_kokoro_wav(
        self,
        kokoro: Any,
        text: str,
        voice_name: str,
    ) -> bytes:
        import soundfile as sf

        samples, sample_rate = kokoro.create(
            text, voice=voice_name, speed=1.0, lang="en-us"
        )
        buf = io.BytesIO()
        sf.write(buf, samples, sample_rate, format="WAV", subtype="PCM_16")
        return buf.getvalue()

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
        except httpx.HTTPError as exc:
            logger.exception("TTS cloud synthesis failed: %s", exc)
            return None
        if resp.status_code != 200:
            logger.warning(
                "TTS cloud synthesis failed: HTTP %d", resp.status_code
            )
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
