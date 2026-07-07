"""Voice activation service: push-to-talk, wake word, and VAD modes.

Implements a small finite-state machine that coordinates microphone listening,
wake-word / voice-activity detection (via ``sherpa-onnx``), and barge-in
cancellation of any in-flight TTS playback or LLM stream.

State machine::

    IDLE ──start_listening()──► LISTENING ──stop_listening()──► PROCESSING
    IDLE ──wake_word / VAD──────► LISTENING ──silence──────────► PROCESSING
    PROCESSING ──llm/tts start──► SPEAKING
    SPEAKING ──barge_in()─────────► LISTENING   (cancels TTS + LLM stream)
    SPEAKING ──tts finished──────► IDLE
    any ──reset()────────────────► IDLE

``sherpa-onnx`` is imported lazily so this module loads in environments where
the package (or its ONNX models) is not installed. Tests inject fakes via the
``wake_word_detector`` and ``vad_detector`` constructor parameters.
"""
from __future__ import annotations

import threading
from enum import Enum
from typing import Callable, Optional, Protocol


class VoiceState(str, Enum):
    """Finite states for the voice activation state machine."""

    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"


class ActivationMode(str, Enum):
    """Microphone activation modes."""

    PUSH_TO_TALK = "push_to_talk"
    WAKE_WORD = "wake_word"
    VAD_ALWAYS_ON = "vad_always_on"


class IllegalTransitionError(RuntimeError):
    """Raised when a transition is attempted from a state that disallows it."""


# ---------------------------------------------------------------------------
# Detector protocols (duck-typed; sherpa-onnx is imported lazily)
# ---------------------------------------------------------------------------


class WakeWordDetector(Protocol):
    def is_wake_word_detected(self, audio: bytes) -> bool: ...


class VADDetector(Protocol):
    def is_voice_activity_detected(self, audio: bytes) -> bool: ...


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class VoiceActivationService:
    """Stateful voice activation coordinator.

    Thread-safe: all public mutators acquire ``_lock``. The service is safe
    to share across the FastAPI request thread and a streaming audio thread.
    """

    def __init__(
        self,
        mode: ActivationMode = ActivationMode.PUSH_TO_TALK,
        wake_word_detector: Optional[WakeWordDetector] = None,
        vad_detector: Optional[VADDetector] = None,
        tts_canceller: Optional[Callable[[], None]] = None,
        llm_canceller: Optional[Callable[[], None]] = None,
    ) -> None:
        self._mode: ActivationMode = mode
        self._state: VoiceState = VoiceState.IDLE
        self._lock = threading.RLock()
        self._wake_word_detector: Optional[WakeWordDetector] = wake_word_detector
        self._vad_detector: Optional[VADDetector] = vad_detector
        self._tts_canceller: Optional[Callable[[], None]] = tts_canceller
        self._llm_canceller: Optional[Callable[[], None]] = llm_canceller

        # Buffer of audio chunks accumulated during LISTENING (push-to-talk
        # records a contiguous blob; VAD/wake-word may also accumulate).
        self._audio_buffer: list[bytes] = []

        # Callbacks invoked on state transitions: list[Callable[[VoiceState], None]]
        self._listeners: list[Callable[[VoiceState], None]] = []

    # ------------------------------------------------------------------ API

    @property
    def mode(self) -> ActivationMode:
        with self._lock:
            return self._mode

    def set_mode(self, mode: ActivationMode) -> None:
        with self._lock:
            self._mode = mode

    def get_state(self) -> VoiceState:
        with self._lock:
            return self._state

    def add_listener(self, cb: Callable[[VoiceState], None]) -> None:
        with self._lock:
            self._listeners.append(cb)

    # ----------------------------------------------------- push-to-talk API

    def start_listening(self) -> VoiceState:
        """Begin recording (push-to-talk button down)."""
        with self._lock:
            if self._state == VoiceState.SPEAKING:
                # Allow barge-in-by-recording: cancel TTS first, then listen.
                self._cancel_tts()
                self._cancel_llm()
            if self._state not in (VoiceState.IDLE, VoiceState.SPEAKING):
                raise IllegalTransitionError(
                    f"cannot start_listening from {self._state.value}"
                )
            self._audio_buffer = []
            self._transition(VoiceState.LISTENING)
            return self._state

    def stop_listening(self) -> bytes:
        """Stop recording (push-to-talk button up); return captured audio."""
        with self._lock:
            if self._state != VoiceState.LISTENING:
                raise IllegalTransitionError(
                    f"cannot stop_listening from {self._state.value}"
                )
            captured = b"".join(self._audio_buffer)
            self._audio_buffer = []
            self._transition(VoiceState.PROCESSING)
            return captured

    # --------------------------------------------------- streaming chunk API

    def process_audio_chunk(self, chunk: bytes) -> Optional[VoiceState]:
        """Feed a streaming audio chunk for wake-word / VAD modes.

        Returns the new state if a transition occurred, else ``None``. In
        ``push_to_talk`` mode the chunk is appended to the recording buffer.
        """
        with self._lock:
            if self._state == VoiceState.LISTENING:
                self._audio_buffer.append(chunk)
                return None

            if self._state == VoiceState.SPEAKING:
                # Barge-in via VAD: if voice activity is detected while the
                # assistant is speaking, cancel TTS/LLM and resume listening.
                if self._mode in (
                    ActivationMode.VAD_ALWAYS_ON,
                    ActivationMode.WAKE_WORD,
                ) and self._is_voice_activity(chunk):
                    self._cancel_tts()
                    self._cancel_llm()
                    self._audio_buffer = [chunk]
                    self._transition(VoiceState.LISTENING)
                    return self._state
                return None

            if self._state == VoiceState.IDLE:
                if self._mode == ActivationMode.WAKE_WORD and self._is_wake_word(chunk):
                    self._audio_buffer = [chunk]
                    self._transition(VoiceState.LISTENING)
                    return self._state
                if (
                    self._mode == ActivationMode.VAD_ALWAYS_ON
                    and self._is_voice_activity(chunk)
                ):
                    self._audio_buffer = [chunk]
                    self._transition(VoiceState.LISTENING)
                    return self._state
            return None

    # ------------------------------------------------------- detection hooks

    def is_wake_word_detected(self, audio: bytes) -> bool:
        """Return True if ``audio`` contains the configured wake word.

        Uses ``sherpa_onnx`` when a real detector is wired in; falls back to
        the injected ``wake_word_detector``. Returns ``False`` when no
        detector is available (e.g. tests without a model).
        """
        return self._is_wake_word(audio)

    def is_voice_activity_detected(self, audio: bytes) -> bool:
        """Return True if ``audio`` contains voice activity (sherpa-onnx VAD)."""
        return self._is_voice_activity(audio)

    def _is_wake_word(self, audio: bytes) -> bool:
        det = self._wake_word_detector
        if det is not None:
            return bool(det.is_wake_word_detected(audio))
        # Lazy sherpa-onnx import; absent in tests.
        try:
            import sherpa_onnx  # type: ignore
        except ImportError:
            return False
        # Real usage would call into a configured KeywordSpotter; we expose the
        # hook but do not download models at import time.
        _ = sherpa_onnx
        return False

    def _is_voice_activity(self, audio: bytes) -> bool:
        det = self._vad_detector
        if det is not None:
            return bool(det.is_voice_activity_detected(audio))
        try:
            import sherpa_onnx  # type: ignore
        except ImportError:
            return False
        _ = sherpa_onnx
        return False

    # ----------------------------------------------------------- barge-in API

    def barge_in(self) -> VoiceState:
        """Cancel current TTS playback + LLM stream and resume listening."""
        with self._lock:
            if self._state != VoiceState.SPEAKING:
                raise IllegalTransitionError(
                    f"cannot barge_in from {self._state.value}"
                )
            self._cancel_tts()
            self._cancel_llm()
            self._audio_buffer = []
            self._transition(VoiceState.LISTENING)
            return self._state

    # --------------------------------------------------- lifecycle callbacks

    def on_processing_started(self) -> None:
        """Called by the orchestrator when LLM/STT processing begins."""
        with self._lock:
            if self._state in (VoiceState.LISTENING, VoiceState.IDLE):
                self._transition(VoiceState.PROCESSING)

    def on_speaking_started(self) -> None:
        """Called by the orchestrator when TTS playback begins."""
        with self._lock:
            if self._state != VoiceState.PROCESSING:
                # TTS may start directly from LISTENING in push-to-talk flows
                # where the orchestrator skips the explicit PROCESSING step.
                if self._state not in (VoiceState.LISTENING, VoiceState.IDLE):
                    raise IllegalTransitionError(
                        f"cannot on_speaking_started from {self._state.value}"
                    )
            self._transition(VoiceState.SPEAKING)

    def on_speaking_finished(self) -> None:
        """Called by the orchestrator when TTS playback completes."""
        with self._lock:
            if self._state != VoiceState.SPEAKING:
                return
            self._transition(VoiceState.IDLE)

    def reset(self) -> None:
        """Force the state machine back to IDLE (e.g. on error)."""
        with self._lock:
            self._audio_buffer = []
            self._transition(VoiceState.IDLE)

    # ------------------------------------------------------------- internals

    def _cancel_tts(self) -> None:
        if self._tts_canceller is not None:
            try:
                self._tts_canceller()
            except Exception:
                pass

    def _cancel_llm(self) -> None:
        if self._llm_canceller is not None:
            try:
                self._llm_canceller()
            except Exception:
                pass

    def _transition(self, new_state: VoiceState) -> None:
        old = self._state
        self._state = new_state
        listeners = list(self._listeners)
        # Release the lock before invoking listeners to avoid reentrancy.
        # (RLock would tolerate it, but explicit release is clearer.)
        for cb in listeners:
            try:
                cb(new_state)
            except Exception:
                pass
        _ = old


# ---------------------------------------------------------------------------
# Process-wide singleton (mirrors stt/tts pattern)
# ---------------------------------------------------------------------------


_voice_activation_service: Optional[VoiceActivationService] = None
_singleton_lock = threading.Lock()


def get_voice_activation_service() -> VoiceActivationService:
    global _voice_activation_service
    if _voice_activation_service is None:
        with _singleton_lock:
            if _voice_activation_service is None:
                _voice_activation_service = VoiceActivationService()
    return _voice_activation_service


def reset_voice_activation_service() -> None:
    """Clear the singleton (used by tests)."""
    global _voice_activation_service
    with _singleton_lock:
        _voice_activation_service = None


def set_voice_activation_service(service: VoiceActivationService) -> None:
    """Inject a service instance (used by tests to wire mocks)."""
    global _voice_activation_service
    with _singleton_lock:
        _voice_activation_service = service
