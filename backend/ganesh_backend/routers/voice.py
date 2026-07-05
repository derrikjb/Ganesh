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
from ganesh_backend.services.tts import TTSError, get_tts_service

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
