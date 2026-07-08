"""Speech-to-Text (STT) service layer.

Primary engine: ``faster-whisper`` (CTranslate2-backed Whisper) running locally
on CPU. The Whisper model is loaded lazily on first use and cached for the
process lifetime so repeated transcriptions do not pay the load cost again.

Cloud fallback: Deepgram API. If the local engine is unavailable (package not
installed, model missing) or transcription fails, the service falls back to
Deepgram over HTTP. The Deepgram API key is resolved from the OS keyring (via
:mod:`ganesh_backend.services.config`) with a fallback to the
``DEEPGRAM_API_KEY`` environment variable.

Both engines return a :class:`TranscriptionResult` with the recognised text, a
normalised confidence score in ``[0.0, 1.0]``, and the engine name that
produced the result (``"local"`` or ``"cloud"``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

import httpx

from ganesh_backend.services.config import config_service

DEFAULT_MODEL: str = "tiny"

# Deepgram cloud endpoint (HTTPS, multipart-less — raw audio bytes POSTed).
DEEPGRAM_URL: str = "https://api.deepgram.com/v1/listen"


@dataclass
class TranscriptionResult:
    """Normalised STT output shared by both engines."""

    text: str
    confidence: float
    engine: str  # "local" | "cloud"


class STTError(RuntimeError):
    """Generic STT failure (model load failure, cloud 4xx/5xx, ...)."""


class STTUnavailableError(STTError):
    """The local engine is not available (package missing, model missing)."""


class MissingDeepgramKeyError(STTError):
    """Cloud fallback requested but no Deepgram API key is configured."""


# ---------------------------------------------------------------------------
# Local engine (faster-whisper)
# ---------------------------------------------------------------------------

# Module-level model cache. ``None`` means "not loaded yet". We deliberately
# do NOT import faster_whisper at module load time so that environments
# without the package (or with a broken CTranslate2 install) can still import
# the service module and report `is_local_available() == False`.
_model_cache: Any = None


def reset_model_cache() -> None:
    """Clear the cached Whisper model so the next call reloads it.

    Primarily for tests; also useful if the user changes the configured model
    name at runtime.
    """
    global _model_cache
    _model_cache = None


def is_local_available() -> bool:
    """Return True if the ``faster_whisper`` package is importable.

    Does NOT verify a model is downloaded — only that the engine code is
    present. Cheap to call (no model load, no network).
    """
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def is_model_loaded() -> bool:
    """Return True if a Whisper model is currently resident in memory."""
    return _model_cache is not None


def _resolve_device() -> tuple[str, str]:
    """Resolve the CTranslate2 device and compute type from config.

    Returns (device, compute_type). When ``voice.stt_device`` is ``"auto"``,
    CUDA is used if available with float16; otherwise CPU with int8.
    ``"cpu"`` forces int8 on CPU. ``"cuda"`` forces float16 on GPU and
    raises if no CUDA device is present.
    """
    preference = config_service.get_setting("voice.stt_device", "auto")
    if preference == "cpu":
        return "cpu", "int8"
    if preference == "cuda":
        if _cuda_device_count() == 0:
            raise STTError("stt_device is 'cuda' but no CUDA device was found")
        return "cuda", "float16"
    # auto: use CUDA if available, else CPU
    if _cuda_device_count() > 0:
        return "cuda", "float16"
    return "cpu", "int8"


def _cuda_device_count() -> int:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


def is_cuda_available() -> bool:
    return _cuda_device_count() > 0


def _load_local_model(model_name: str = DEFAULT_MODEL) -> Any:
    """Load (or return cached) faster-whisper model.

    Raises:
        STTUnavailableError: package not installed.
        STTError: model load failed (download error, corrupt weights, ...).
    """
    global _model_cache
    if _model_cache is not None:
        return _model_cache

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise STTUnavailableError(
            "faster-whisper is not installed; local STT unavailable"
        ) from exc

    device, compute_type = _resolve_device()

    try:
        _model_cache = WhisperModel(model_name, device=device, compute_type=compute_type)
    except Exception as exc:  # noqa: BLE001 - many failure modes from CT2
        _model_cache = None
        raise STTError(f"failed to load Whisper model '{model_name}' on {device}: {exc}") from exc

    return _model_cache


def _segments_to_text_and_confidence(
    segments_iter: Any, info: Any
) -> tuple[str, float]:
    """Flatten faster-whisper segments into (text, avg_confidence).

    faster-whisper yields segment objects with ``.text`` and ``.avg_logprob``.
    ``info.language_probability`` is the language detection confidence but
    does not reflect transcription quality; we average per-segment
    ``avg_logprob`` (which is a log-probability in roughly [-inf, 0]) and
    convert to a [0, 1] confidence via a logistic-style squashing.
    """
    texts: list[str] = []
    logprobs: list[float] = []
    for seg in segments_iter:
        text = getattr(seg, "text", None)
        if text:
            texts.append(text.strip())
        lp = getattr(seg, "avg_logprob", None)
        if lp is not None:
            logprobs.append(float(lp))

    joined = " ".join(texts).strip()
    if not logprobs:
        confidence = 0.0
    else:
        avg_lp = sum(logprobs) / len(logprobs)
        # avg_logprob is typically in [-1.0, 0.0] for good transcriptions.
        # Map: 0.0 -> 1.0, -1.0 -> ~0.27, worse -> lower. Clamp to [0, 1].
        confidence = max(0.0, min(1.0, math.exp(avg_lp)))
    return joined, confidence


def transcribe_local(
    audio_path: str,
    language: Optional[str] = None,
    model_name: Optional[str] = None,
) -> TranscriptionResult:
    """Transcribe ``audio_path`` with the local faster-whisper engine.

    Args:
        audio_path: Path to an audio file readable by ffmpeg/av.
        language: ISO-639-1 language hint (e.g. ``"en"``) or None for auto-detect.
        model_name: Whisper model size (``tiny`` / ``base`` / ``small`` / ...).
            If None, reads from ``voice.whisper_model`` config.

    Raises:
        STTUnavailableError: faster-whisper not installed.
        STTError: model load or transcription failed.
    """
    if model_name is None:
        model_name = config_service.get_setting("voice.whisper_model", DEFAULT_MODEL)
    model = _load_local_model(model_name)
    try:
        segments, info = model.transcribe(audio_path, language=language)
    except Exception as exc:  # noqa: BLE001 - CT2/ffmpeg raise many types
        raise STTError(f"local transcription failed: {exc}") from exc

    text, confidence = _segments_to_text_and_confidence(segments, info)
    return TranscriptionResult(text=text, confidence=confidence, engine="local")


# ---------------------------------------------------------------------------
# Cloud engine (Deepgram)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_deepgram_key() -> str:
    """Resolve the Deepgram API key.

    Order of precedence:
        1. OS keyring via ``config_service.get_voice_provider_key("deepgram")``
           (account ``ganesh_voice_key_deepgram``)
        2. ``DEEPGRAM_API_KEY`` environment variable

    Cached for the process lifetime; call :func:`reset_deepgram_key_cache`
    to force a re-read.
    """
    key: Optional[str] = config_service.get_voice_provider_key("deepgram")
    if not key:
        key = config_service.get_voice_provider_key_env("deepgram")
    if not key:
        raise MissingDeepgramKeyError(
            "No Deepgram API key configured. Set one via the config UI or "
            "the DEEPGRAM_API_KEY environment variable."
        )
    return key


def reset_deepgram_key_cache() -> None:
    """Clear the cached Deepgram key so the next call re-reads from keyring/env."""
    get_deepgram_key.cache_clear()


def _deepgram_params(language: Optional[str]) -> dict[str, str]:
    """Build Deepgram query-string params."""
    params: dict[str, str] = {
        "model": "nova-2",
        "smart_format": "true",
        "punctuate": "true",
    }
    if language:
        params["language"] = language
    return params


def transcribe_cloud(
    audio_path: str,
    language: Optional[str] = None,
    *,
    client: Optional[httpx.AsyncClient] = None,
) -> TranscriptionResult:
    """Transcribe ``audio_path`` with the Deepgram cloud API.

    Args:
        audio_path: Path to an audio file (raw bytes POSTed to Deepgram).
        language: ISO-639-1 language hint or None for auto-detect.
        client: Optional pre-configured ``httpx.AsyncClient`` (for tests with
            ``httpx.MockTransport``). If None, a one-shot client is created.

    Raises:
        MissingDeepgramKeyError: no Deepgram API key configured.
        STTError: HTTP failure or unparseable response.
    """
    api_key = get_deepgram_key()
    params = _deepgram_params(language)
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "application/octet-stream",
    }

    with open(audio_path, "rb") as fh:
        audio_bytes = fh.read()

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        import asyncio

        response = asyncio.get_event_loop().run_until_complete(
            client.post(  # type: ignore[union-attr]
                DEEPGRAM_URL, params=params, headers=headers, content=audio_bytes
            )
        )
    finally:
        if own_client and client is not None:
            import asyncio

            asyncio.get_event_loop().run_until_complete(client.aclose())

    if response.status_code != 200:
        raise STTError(
            f"Deepgram returned HTTP {response.status_code}: "
            f"{response.text[:200]}"
        )

    try:
        data = response.json()
        channel = data["results"]["channels"][0]
        alt = channel["alternatives"][0]
        text = alt.get("transcript", "").strip()
        confidence = float(alt.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
    except (KeyError, ValueError, TypeError) as exc:
        raise STTError(f"unparseable Deepgram response: {exc}") from exc

    return TranscriptionResult(text=text, confidence=confidence, engine="cloud")


async def transcribe_cloud_async(
    audio_path: str,
    language: Optional[str] = None,
    *,
    client: Optional[httpx.AsyncClient] = None,
) -> TranscriptionResult:
    """Async variant of :func:`transcribe_cloud` for use inside FastAPI handlers.

    Avoids the ``run_until_complete`` dance the sync wrapper performs. If
    ``client`` is None a one-shot ``httpx.AsyncClient`` is created and closed
    here.
    """
    api_key = get_deepgram_key()
    params = _deepgram_params(language)
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "application/octet-stream",
    }

    with open(audio_path, "rb") as fh:
        audio_bytes = fh.read()

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        response = await client.post(  # type: ignore[union-attr]
            DEEPGRAM_URL, params=params, headers=headers, content=audio_bytes
        )
    finally:
        if own_client and client is not None:
            await client.aclose()

    if response.status_code != 200:
        raise STTError(
            f"Deepgram returned HTTP {response.status_code}: "
            f"{response.text[:200]}"
        )

    try:
        data = response.json()
        channel = data["results"]["channels"][0]
        alt = channel["alternatives"][0]
        text = alt.get("transcript", "").strip()
        confidence = float(alt.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
    except (KeyError, ValueError, TypeError) as exc:
        raise STTError(f"unparseable Deepgram response: {exc}") from exc

    return TranscriptionResult(text=text, confidence=confidence, engine="cloud")


# ---------------------------------------------------------------------------
# Orchestrator: local-first, cloud-fallback
# ---------------------------------------------------------------------------


def transcribe(
    audio_path: str,
    language: Optional[str] = None,
    *,
    cloud_client: Optional[httpx.AsyncClient] = None,
) -> TranscriptionResult:
    """Transcribe ``audio_path`` using local engine with cloud fallback.

    Engine order is controlled by ``voice.stt_engine`` config:
        - ``"local"`` (default): try local first, fall back to cloud.
        - ``"cloud"``: try cloud first, fall back to local.

    Args:
        audio_path: Path to an audio file.
        language: ISO-639-1 language hint or None for auto-detect.
        cloud_client: Optional ``httpx.AsyncClient`` for the cloud call
            (test injection point; production passes None).

    Raises:
        STTError: Both engines failed.
    """
    engine_pref = config_service.get_setting("voice.stt_engine", "local")
    if engine_pref == "cloud":
        return _transcribe_cloud_first(audio_path, language, cloud_client=cloud_client)
    return _transcribe_local_first(audio_path, language, cloud_client=cloud_client)


def _transcribe_local_first(
    audio_path: str,
    language: Optional[str],
    *,
    cloud_client: Optional[httpx.AsyncClient],
) -> TranscriptionResult:
    local_error: Optional[Exception] = None
    try:
        return transcribe_local(audio_path, language=language)
    except Exception as exc:  # noqa: BLE001 - any local failure -> fallback
        local_error = exc

    try:
        return transcribe_cloud(audio_path, language=language, client=cloud_client)
    except STTError as cloud_exc:
        raise STTError(
            f"local STT failed ({local_error}); cloud fallback also failed "
            f"({cloud_exc})"
        ) from cloud_exc


def _transcribe_cloud_first(
    audio_path: str,
    language: Optional[str],
    *,
    cloud_client: Optional[httpx.AsyncClient],
) -> TranscriptionResult:
    cloud_error: Optional[Exception] = None
    try:
        return transcribe_cloud(audio_path, language=language, client=cloud_client)
    except Exception as exc:  # noqa: BLE001 - any cloud failure -> fallback
        cloud_error = exc

    try:
        return transcribe_local(audio_path, language=language)
    except STTError as local_exc:
        raise STTError(
            f"cloud STT failed ({cloud_error}); local fallback also failed "
            f"({local_exc})"
        ) from local_exc


async def transcribe_async(
    audio_path: str,
    language: Optional[str] = None,
    *,
    cloud_client: Optional[httpx.AsyncClient] = None,
) -> TranscriptionResult:
    """Async orchestrator variant — uses :func:`transcribe_cloud_async`.

    Engine order is controlled by ``voice.stt_engine`` config (same as
    :func:`transcribe`). Preferred inside FastAPI route handlers (no nested
    event loop).
    """
    engine_pref = config_service.get_setting("voice.stt_engine", "local")
    if engine_pref == "cloud":
        return await _transcribe_cloud_first_async(
            audio_path, language, cloud_client=cloud_client
        )
    return await _transcribe_local_first_async(
        audio_path, language, cloud_client=cloud_client
    )


async def _transcribe_local_first_async(
    audio_path: str,
    language: Optional[str],
    *,
    cloud_client: Optional[httpx.AsyncClient],
) -> TranscriptionResult:
    local_error: Optional[Exception] = None
    try:
        return transcribe_local(audio_path, language=language)
    except Exception as exc:  # noqa: BLE001
        local_error = exc

    try:
        return await transcribe_cloud_async(
            audio_path, language=language, client=cloud_client
        )
    except STTError as cloud_exc:
        raise STTError(
            f"local STT failed ({local_error}); cloud fallback also failed "
            f"({cloud_exc})"
        ) from cloud_exc


async def _transcribe_cloud_first_async(
    audio_path: str,
    language: Optional[str],
    *,
    cloud_client: Optional[httpx.AsyncClient],
) -> TranscriptionResult:
    cloud_error: Optional[Exception] = None
    try:
        return await transcribe_cloud_async(
            audio_path, language=language, client=cloud_client
        )
    except Exception as exc:  # noqa: BLE001
        cloud_error = exc

    try:
        return transcribe_local(audio_path, language=language)
    except STTError as local_exc:
        raise STTError(
            f"cloud STT failed ({cloud_error}); local fallback also failed "
            f"({local_exc})"
        ) from local_exc
