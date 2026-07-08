import { useCallback, useEffect, useRef, useState } from 'react'
import { sidecarFetch } from '../api'

interface TranscribeResponse {
  text: string
  confidence: number
  engine: string
}

interface UseVoiceRecordingResult {
  isRecording: boolean
  isTranscribing: boolean
  transcript: string
  error: string | null
  start: () => Promise<void>
  stop: () => Promise<void>
}

function pickMimeType(): string {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
  ]
  if (typeof MediaRecorder === 'undefined') return ''
  for (const type of candidates) {
    if (MediaRecorder.isTypeSupported(type)) return type
  }
  return ''
}

export function useVoiceRecording(): UseVoiceRecordingResult {
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mediaStreamRef = useRef<MediaStream | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const mimeTypeRef = useRef<string>('')

  const cleanupStream = useCallback(() => {
    const stream = mediaStreamRef.current
    if (stream) {
      for (const track of stream.getTracks()) {
        track.stop()
      }
      mediaStreamRef.current = null
    }
    recorderRef.current = null
    chunksRef.current = []
  }, [])

  useEffect(() => {
    return () => {
      cleanupStream()
    }
  }, [cleanupStream])

  const start = useCallback(async () => {
    setError(null)
    setTranscript('')
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setError('Microphone access is not supported in this environment.')
      return
    }
    if (typeof MediaRecorder === 'undefined') {
      setError('Audio recording is not supported in this environment.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaStreamRef.current = stream
      const mimeType = pickMimeType()
      mimeTypeRef.current = mimeType
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream)
      chunksRef.current = []
      recorder.ondataavailable = (e: BlobEvent) => {
        if (e.data && e.data.size > 0) {
          chunksRef.current.push(e.data)
        }
      }
      recorderRef.current = recorder
      recorder.start()
      setIsRecording(true)
    } catch (err) {
      const message =
        err instanceof DOMException && err.name === 'NotAllowedError'
          ? 'Microphone permission denied.'
          : err instanceof Error
            ? err.message
            : 'Failed to start recording.'
      setError(message)
      cleanupStream()
      setIsRecording(false)
    }
  }, [cleanupStream])

  const stop = useCallback(async () => {
    const recorder = recorderRef.current
    if (!recorder || recorder.state === 'inactive') {
      setIsRecording(false)
      cleanupStream()
      return
    }

    const mimeType = mimeTypeRef.current
    const chunks = chunksRef.current

    await new Promise<void>((resolve) => {
      recorder.onstop = () => resolve()
      recorder.stop()
    })

    setIsRecording(false)
    cleanupStream()

    if (chunks.length === 0) {
      setError('No audio was captured.')
      return
    }

    const blob = new Blob(chunks, { type: mimeType || 'audio/webm' })
    if (blob.size === 0) {
      setError('No audio was captured.')
      return
    }

    setIsTranscribing(true)
    try {
      const form = new FormData()
      const ext = mimeType.includes('mp4')
        ? 'mp4'
        : mimeType.includes('ogg')
          ? 'ogg'
          : 'webm'
      form.append('file', blob, `recording.${ext}`)
      const res = await sidecarFetch('/api/voice/transcribe', {
        method: 'POST',
        body: form,
      })
      if (!res.ok) {
        throw new Error(`Transcription failed with status ${res.status}`)
      }
      const data = (await res.json()) as TranscribeResponse
      setTranscript(data.text ?? '')
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Transcription request failed.'
      setError(message)
    } finally {
      setIsTranscribing(false)
    }
  }, [cleanupStream])

  return { isRecording, isTranscribing, transcript, error, start, stop }
}
