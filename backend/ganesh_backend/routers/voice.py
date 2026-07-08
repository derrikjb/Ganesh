"""Voice router: STT + TTS endpoints for the Ganesh sidecar.

Exposes:
    POST /api/voice/transcribe   — multipart audio upload -> transcription
    GET  /api/voice/stt-status    — local STT engine availability + model state
    POST /api/voice/synthesize    — text -> audio (Piper local + ElevenLabs cloud)
    GET  /api/voice/tts-status    — TTS backend availability
    GET  /api/voice/voices        — list available TTS voices
"""
from __future__ import annotations

import os
import tempfile
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from ganesh_backend.services import stt as stt_service
from ganesh_backend.services.config import config_service, SUPPORTED_VOICE_PROVIDERS
from ganesh_backend.services.tts import TTSError, get_tts_service
from ganesh_backend.services.voice_activation import (
    ActivationMode,
    IllegalTransitionError,
    VoiceState,
    get_voice_activation_service,
    reset_voice_activation_service,
    set_voice_activation_service,
    VoiceActivationService,
)

router = APIRouter(prefix="/api/voice", tags=["voice"])

# 25 MiB upload cap — plenty for a short voice memo, blocks accidental huge
# uploads that would blow the sidecar's memory budget.
MAX_AUDIO_BYTES: int = 25 * 1024 * 1024


class TranscriptionResponse(BaseModel):
    text: str
    confidence: float
    engine: str


class STTStatus(BaseModel):
    local_available: bool
    model_loaded: bool
    cloud_available: bool


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(
    file: Optional[UploadFile] = File(default=None),
    language: Optional[str] = Form(default=None),
) -> Any:
    if file is None or not file.filename:
        raise HTTPException(status_code=400, detail="no audio file uploaded")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"audio too large: {len(audio_bytes)} > {MAX_AUDIO_BYTES} bytes",
        )

    # Spool to a temp file so faster-whisper (which uses ffmpeg/av to demux)
    # and Deepgram (which takes raw bytes) both get a real path to read.
    suffix = os.path.splitext(file.filename or "")[1] or ".wav"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(audio_bytes)
        tmp.flush()
        tmp.close()
        try:
            result = await stt_service.transcribe_async(
                tmp.name, language=language
            )
        except stt_service.MissingDeepgramKeyError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except stt_service.STTError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    return TranscriptionResponse(
        text=result.text, confidence=result.confidence, engine=result.engine
    )


@router.get("/stt-status", response_model=STTStatus)
async def stt_status() -> Any:
    cloud_available = True
    try:
        stt_service.get_deepgram_key()
    except stt_service.STTError:
        cloud_available = False

    return STTStatus(
        local_available=stt_service.is_local_available(),
        model_loaded=stt_service.is_model_loaded(),
        cloud_available=cloud_available,
    )


class SynthesizeRequest(BaseModel):
    text: str = Field(..., description="Text to synthesize.")
    voice: Optional[str] = Field(
        None, description="Optional voice id or Piper model path override."
    )


class TtsStatusResponse(BaseModel):
    available: bool
    local: bool
    cloud: bool


class VoiceInfo(BaseModel):
    id: str
    name: str
    backend: str


class VoicesResponse(BaseModel):
    voices: list[VoiceInfo]


@router.post("/synthesize")
async def synthesize(req: SynthesizeRequest) -> Response:
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="text must be non-empty")

    service = get_tts_service()
    try:
        audio_bytes, content_type, _source = service.synthesize(
            req.text, voice=req.voice
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TTSError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return Response(content=audio_bytes, media_type=content_type)


@router.get("/tts-status", response_model=TtsStatusResponse)
async def tts_status() -> Any:
    service = get_tts_service()
    return TtsStatusResponse(
        available=service.is_available(),
        local=service._local_available(),
        cloud=service._cloud_available(),
    )


@router.get("/voices", response_model=VoicesResponse)
async def voices() -> Any:
    service = get_tts_service()
    return VoicesResponse(
        voices=[VoiceInfo(**v) for v in service.list_voices()]
    )


# ---------------------------------------------------------------------------
# Voice settings: STT/TTS engine selection, whisper model, piper voice mgmt
# ---------------------------------------------------------------------------


class VoiceSettingsResponse(BaseModel):
    stt_engine: str
    tts_engine: str
    whisper_model: str
    stt_device: str
    tts_device: str
    deepgram_model: str
    elevenlabs_voice_id: str
    piper_voices: list[dict[str, Any]]
    piper_active_voice: Optional[str]
    stt_local_available: bool
    stt_cloud_available: bool
    tts_local_available: bool
    tts_cloud_available: bool
    cuda_available: bool


class VoiceSettingsUpdate(BaseModel):
    stt_engine: Optional[str] = None
    tts_engine: Optional[str] = None
    whisper_model: Optional[str] = None
    stt_device: Optional[str] = None
    tts_device: Optional[str] = None
    deepgram_model: Optional[str] = None
    elevenlabs_voice_id: Optional[str] = None
    piper_active_voice: Optional[str] = None


class AddPiperVoiceRequest(BaseModel):
    name: str
    path: str


class VoiceKeyUpdate(BaseModel):
    api_key: str


def _build_voice_settings() -> VoiceSettingsResponse:
    service = get_tts_service()
    cloud_available = True
    try:
        stt_service.get_deepgram_key()
    except stt_service.STTError:
        cloud_available = False
    return VoiceSettingsResponse(
        stt_engine=config_service.get_setting("voice.stt_engine", "local"),
        tts_engine=config_service.get_setting("voice.tts_engine", "local"),
        whisper_model=config_service.get_setting("voice.whisper_model", "tiny"),
        stt_device=config_service.get_setting("voice.stt_device", "auto"),
        tts_device=config_service.get_setting("voice.tts_device", "auto"),
        deepgram_model=config_service.get_setting("voice.deepgram_model", "nova-2"),
        elevenlabs_voice_id=config_service.get_setting(
            "voice.elevenlabs_voice_id", "21m00Tcm4TlvDq8ikWAM"
        ),
        piper_voices=config_service.get_setting("voice.piper_voices", []),
        piper_active_voice=config_service.get_setting("voice.piper_active_voice"),
        stt_local_available=stt_service.is_local_available(),
        stt_cloud_available=cloud_available,
        tts_local_available=service._local_available(),
        tts_cloud_available=service._cloud_available(),
        cuda_available=stt_service.is_cuda_available(),
    )


@router.get("/settings", response_model=VoiceSettingsResponse)
async def get_voice_settings() -> Any:
    return _build_voice_settings()


@router.put("/settings", response_model=VoiceSettingsResponse)
async def update_voice_settings(req: VoiceSettingsUpdate) -> Any:
    updates = req.dict(exclude_none=True)
    old_whisper = config_service.get_setting("voice.whisper_model", "tiny")
    old_device = config_service.get_setting("voice.stt_device", "auto")
    for key, value in updates.items():
        config_service.set_setting(f"voice.{key}", value)
    if "whisper_model" in updates and updates["whisper_model"] != old_whisper:
        stt_service.reset_model_cache()
    if "stt_device" in updates and updates["stt_device"] != old_device:
        stt_service.reset_model_cache()
    old_tts_device = config_service.get_setting("voice.tts_device", "auto")
    if "tts_device" in updates and updates["tts_device"] != old_tts_device:
        service = get_tts_service()
        service._voice_cache.clear()
    return _build_voice_settings()


@router.post("/piper-voices")
async def add_piper_voice(req: AddPiperVoiceRequest) -> dict[str, Any]:
    service = get_tts_service()
    voice = service.add_voice(req.name, req.path)
    return voice


@router.delete("/piper-voices/{voice_id}", status_code=204)
async def delete_piper_voice(voice_id: str) -> Response:
    service = get_tts_service()
    service.remove_voice(voice_id)
    return Response(status_code=204)


@router.post("/piper-voices/{voice_id}/activate", response_model=VoiceSettingsResponse)
async def activate_piper_voice(voice_id: str) -> Any:
    service = get_tts_service()
    service.set_active_voice(voice_id)
    return _build_voice_settings()


@router.post("/keys/{provider}")
async def store_voice_provider_key(
    provider: str, update: VoiceKeyUpdate
) -> dict[str, str]:
    if provider not in SUPPORTED_VOICE_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown voice provider: {provider!r}",
        )
    try:
        config_service.set_voice_provider_key(provider, update.api_key)
        if provider == "deepgram":
            stt_service.reset_deepgram_key_cache()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.get("/keys/{provider}/status")
async def voice_provider_key_status(provider: str) -> dict[str, bool]:
    if provider not in SUPPORTED_VOICE_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown voice provider: {provider!r}",
        )
    return {"configured": config_service.is_voice_provider_configured(provider)}


# ---------------------------------------------------------------------------
# Voice activation: push-to-talk / wake-word / VAD + barge-in state machine
# ---------------------------------------------------------------------------


class VoiceStateResponse(BaseModel):
    state: VoiceState
    mode: ActivationMode


class SetModeRequest(BaseModel):
    mode: ActivationMode


class AudioChunkRequest(BaseModel):
    chunk: bytes = Field(..., description="Raw audio chunk (base64-safe bytes).")


class BargeInResponse(BaseModel):
    state: VoiceState
    cancelled_tts: bool
    cancelled_llm: bool


@router.get("/state", response_model=VoiceStateResponse)
async def voice_state() -> Any:
    service = get_voice_activation_service()
    return VoiceStateResponse(state=service.get_state(), mode=service.mode)


@router.post("/set-mode", response_model=VoiceStateResponse)
async def set_voice_mode(req: SetModeRequest) -> Any:
    service = get_voice_activation_service()
    service.set_mode(req.mode)
    return VoiceStateResponse(state=service.get_state(), mode=service.mode)


@router.post("/start-listening", response_model=VoiceStateResponse)
async def start_listening() -> Any:
    service = get_voice_activation_service()
    try:
        service.start_listening()
    except IllegalTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return VoiceStateResponse(state=service.get_state(), mode=service.mode)


@router.post("/stop-listening")
async def stop_listening() -> Any:
    service = get_voice_activation_service()
    try:
        captured = service.stop_listening()
    except IllegalTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "state": service.get_state(),
        "mode": service.mode,
        "audio_size": len(captured),
    }


@router.post("/audio-chunk", response_model=VoiceStateResponse)
async def audio_chunk(req: AudioChunkRequest) -> Any:
    service = get_voice_activation_service()
    new_state = service.process_audio_chunk(req.chunk)
    if new_state is None:
        return VoiceStateResponse(state=service.get_state(), mode=service.mode)
    return VoiceStateResponse(state=new_state, mode=service.mode)


@router.post("/barge-in", response_model=BargeInResponse)
async def barge_in() -> Any:
    service = get_voice_activation_service()
    try:
        service.barge_in()
    except IllegalTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return BargeInResponse(
        state=service.get_state(),
        cancelled_tts=True,
        cancelled_llm=True,
    )


@router.post("/reset", response_model=VoiceStateResponse)
async def reset_voice_state() -> Any:
    service = get_voice_activation_service()
    service.reset()
    return VoiceStateResponse(state=service.get_state(), mode=service.mode)


__all__ = [
    "set_voice_activation_service",
    "reset_voice_activation_service",
    "VoiceActivationService",
]
