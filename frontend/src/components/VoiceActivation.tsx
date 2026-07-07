import { useCallback, useEffect, useRef, useState } from 'react'
import { sidecarFetch } from '../api'

export type ActivationMode = 'push_to_talk' | 'wake_word' | 'vad_always_on'
export type VoiceState = 'idle' | 'listening' | 'processing' | 'speaking'
export type MicStatus = 'idle' | 'requesting' | 'recording' | 'listening' | 'denied' | 'error'

interface VoiceActivationProps {
  onTranscription?: (text: string) => void
}

interface StateResponse {
  state: VoiceState
  mode: ActivationMode
}

function mockResponse(body: unknown, init: { ok?: boolean; status?: number } = {}): Response {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => body,
  } as unknown as Response
}

export function VoiceActivation({ onTranscription }: VoiceActivationProps = {}) {
  const [mode, setMode] = useState<ActivationMode>('push_to_talk')
  const [voiceState, setVoiceState] = useState<VoiceState>('idle')
  const [micStatus, setMicStatus] = useState<MicStatus>('idle')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const mediaStreamRef = useRef<MediaStream | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunkBufferRef = useRef<Blob[]>([])
  const vadIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)

  const refreshState = useCallback(async () => {
    try {
      const res = await sidecarFetch('/api/voice/state')
      if (res.ok) {
        const body = (await res.json()) as StateResponse
        setVoiceState(body.state)
        setMode(body.mode)
      }
    } catch {
      // sidecar not ready yet
    }
  }, [])

  useEffect(() => {
    void refreshState()
  }, [refreshState])

  const stopVadInterval = useCallback(() => {
    if (vadIntervalRef.current !== null) {
      clearInterval(vadIntervalRef.current)
      vadIntervalRef.current = null
    }
  }, [])

  const stopStream = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    mediaRecorderRef.current = null
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop())
      mediaStreamRef.current = null
    }
    if (audioContextRef.current) {
      void audioContextRef.current.close()
      audioContextRef.current = null
    }
    stopVadInterval()
  }, [stopVadInterval])

  useEffect(() => {
    return () => {
      stopStream()
    }
  }, [stopStream])

  const requestMic = useCallback(async (): Promise<MediaStream | null> => {
    setMicStatus('requesting')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaStreamRef.current = stream
      setMicStatus('recording')
      return stream
    } catch (err) {
      setMicStatus('denied')
      setErrorMsg(err instanceof Error ? err.message : 'Microphone permission denied')
      return null
    }
  }, [])

  const setModeRemote = useCallback(
    async (newMode: ActivationMode) => {
      setMode(newMode)
      try {
        await sidecarFetch('/api/voice/set-mode', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: newMode }),
        })
      } catch {
        // ignore — local state still updates
      }
      if (newMode !== 'push_to_talk') {
        void startStreamingMode(newMode)
      } else {
        stopStream()
        setMicStatus('idle')
      }
    },
     
    [stopStream],
  )

  const startStreamingMode = useCallback(
    async (_targetMode: ActivationMode) => {
      const stream = await requestMic()
      if (!stream) return
      setMicStatus('listening')
      const audioContext = new AudioContext()
      audioContextRef.current = audioContext
      const source = audioContext.createMediaStreamSource(stream)
      const processor = audioContext.createScriptProcessor(4096, 1, 1)
      processor.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0)
        const pcm = floatTo16BitPCM(input)
        void sidecarFetch('/api/voice/audio-chunk', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ chunk: arrayBufferToBase64(pcm.buffer as ArrayBuffer) }),
        }).then(() => void refreshState())
      }
      source.connect(processor)
      processor.connect(audioContext.destination)
    },
    [requestMic, refreshState],
  )

  const startPushToTalk = useCallback(async () => {
    setErrorMsg(null)
    const stream = await requestMic()
    if (!stream) return
    chunkBufferRef.current = []
    const recorder = new MediaRecorder(stream)
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunkBufferRef.current.push(e.data)
    }
    recorder.onstop = () => {
      const blob = new Blob(chunkBufferRef.current, { type: recorder.mimeType })
      void sendRecording(blob)
    }
    recorder.start()
    mediaRecorderRef.current = recorder
    setMicStatus('recording')
    try {
      await sidecarFetch('/api/voice/start-listening', { method: 'POST' })
      void refreshState()
    } catch {
      // sidecar may be unavailable
    }
  }, [requestMic, refreshState])

  const stopPushToTalk = useCallback(async () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    setMicStatus('idle')
    try {
      await sidecarFetch('/api/voice/stop-listening', { method: 'POST' })
      void refreshState()
    } catch {
      // ignore
    }
  }, [refreshState])

  const sendRecording = useCallback(
    async (blob: Blob) => {
      const formData = new FormData()
      formData.append('file', blob, 'recording.webm')
      try {
        const res = await sidecarFetch('/api/voice/transcribe', {
          method: 'POST',
          body: formData,
        })
        if (res.ok) {
          const body = (await res.json()) as { text: string }
          onTranscription?.(body.text)
        }
      } catch {
        // ignore
      }
    },
    [onTranscription],
  )

  const triggerBargeIn = useCallback(async () => {
    try {
      await sidecarFetch('/api/voice/barge-in', { method: 'POST' })
      void refreshState()
    } catch {
      // ignore
    }
  }, [refreshState])

  const statusColor =
    micStatus === 'recording'
      ? 'text-status-error'
      : micStatus === 'listening'
        ? 'text-status-success'
        : micStatus === 'denied' || micStatus === 'error'
          ? 'text-status-error'
          : 'text-text-muted'

  const isRecording = micStatus === 'recording'

  return (
    <div
      className="flex flex-col gap-3 p-4 rounded-lg border border-border bg-bg-secondary"
      data-testid="voice-activation"
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-text-primary">Voice Activation</span>
        <span
          className={`text-xs ${statusColor}`}
          data-testid="mic-status"
        >
          {micStatus}
        </span>
      </div>

      <div className="flex gap-2" data-testid="mode-selector">
        {(['push_to_talk', 'wake_word', 'vad_always_on'] as ActivationMode[]).map((m) => (
          <button
            key={m}
            onClick={() => void setModeRemote(m)}
            className={`px-3 py-1.5 text-xs rounded-md border transition-colors ${
              mode === m
                ? 'border-accent-primary bg-accent-primary/10 text-accent-primary'
                : 'border-border text-text-muted hover:text-text-primary'
            }`}
            data-testid={`mode-${m}`}
            aria-pressed={mode === m}
          >
            {m.replace(/_/g, ' ')}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <button
          onMouseDown={() => void startPushToTalk()}
          onMouseUp={() => void stopPushToTalk()}
          onMouseLeave={() => {
            if (isRecording) void stopPushToTalk()
          }}
          onTouchStart={() => void startPushToTalk()}
          onTouchEnd={() => void stopPushToTalk()}
          disabled={mode !== 'push_to_talk'}
          className={`px-4 py-2 text-sm rounded-md border transition-colors ${
            isRecording
              ? 'border-status-error bg-status-error/10 text-status-error'
              : 'border-border text-text-primary hover:bg-bg-tertiary'
          } ${mode !== 'push_to_talk' ? 'opacity-50 cursor-not-allowed' : ''}`}
          data-testid="push-to-talk-button"
          aria-label="Push to talk"
        >
          {isRecording ? 'Recording…' : 'Hold to talk'}
        </button>

        <button
          onClick={() => void triggerBargeIn()}
          disabled={voiceState !== 'speaking'}
          className="px-3 py-2 text-xs rounded-md border border-border text-text-muted hover:text-status-error disabled:opacity-50"
          data-testid="barge-in-button"
        >
          Barge in
        </button>
      </div>

      <div className="text-xs text-text-muted" data-testid="voice-state">
        State: <span className="text-text-primary">{voiceState}</span>
      </div>

      {errorMsg && (
        <div className="text-xs text-status-error" data-testid="voice-error">
          {errorMsg}
        </div>
      )}
    </div>
  )
}

function floatTo16BitPCM(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length)
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]))
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return out
}

function arrayBufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf)
  let binary = ''
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i])
  }
  return btoa(binary)
}

export { mockResponse }
