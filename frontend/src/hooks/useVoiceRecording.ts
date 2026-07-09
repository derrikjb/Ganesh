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
  resetTranscript: () => void
}

export function useVoiceRecording(): UseVoiceRecordingResult {
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [error, setError] = useState<string | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  const start = useCallback(async () => {
    setError(null)
    setTranscript('')
    try {
      const res = await sidecarFetch('/api/voice/record/start', { method: 'POST' })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? `HTTP ${res.status}`)
      }
      if (mountedRef.current) setIsRecording(true)
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : 'Failed to start recording.')
      }
    }
  }, [])

  const stop = useCallback(async () => {
    setIsRecording(false)
    setIsTranscribing(true)
    try {
      const res = await sidecarFetch('/api/voice/record/stop', { method: 'POST' })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? `HTTP ${res.status}`)
      }
      const data = (await res.json()) as TranscribeResponse
      if (mountedRef.current) {
        if (data.text && data.text.trim()) {
          setTranscript(data.text)
        } else {
          setError('No speech detected in recording.')
        }
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : 'Transcription failed.')
      }
    } finally {
      if (mountedRef.current) setIsTranscribing(false)
    }
  }, [])

  const resetTranscript = useCallback(() => {
    setTranscript('')
  }, [])

  return { isRecording, isTranscribing, transcript, error, start, stop, resetTranscript }
}
