import { useCallback, useEffect, useRef, useState } from 'react'
import { sidecarFetch } from '../api'
import { stripMarkdown } from '../utils/markdown'
import type { UseTTSReturn } from '../types/chat'

export type { UseTTSReturn } from '../types/chat'

const TTS_ENABLED_KEY = 'ganesh_tts_enabled'
const TTS_VOLUME_KEY = 'ganesh_tts_volume'
const TTS_OUTPUT_DEVICE_KEY = 'ganesh_tts_output_device'

async function applySinkId(audio: HTMLAudioElement, sinkId: string): Promise<void> {
  if (!('setSinkId' in audio)) return
  try {
    await (audio as HTMLAudioElement & {
      setSinkId: (id: string) => Promise<void>
    }).setSinkId(sinkId)
  } catch {
    // setSinkId not supported or failed — non-critical
  }
}

/**
 * Find the index of the last natural breakpoint in `text` at or before `end`.
 * Breakpoints: paragraph boundary (\n\n), list item boundary (\n- \n* \n1.),
 * or sentence boundary (. ! ? followed by space/newline).
 * Returns -1 if no breakpoint is found.
 */
function findBreakpoint(text: string, end: number): number {
  const slice = text.slice(0, end)
  const patterns = [
    /\n\n/,
    /\n[-*+]\s/,
    /\n\d+\.\s/,
    /[.!?]\s/,
    /[.!?]$/,
  ]
  let last = -1
  for (const p of patterns) {
    const m = slice.match(p)
    if (m && m.index !== undefined) {
      const pos = m.index + m[0].length
      if (pos > last) last = pos
    }
  }
  return last
}

export function useTTS(): UseTTSReturn {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [isSpeaking, setIsSpeaking] = useState(false)

  const [volume, setVolumeState] = useState<number>(() =>
    Number(localStorage.getItem(TTS_VOLUME_KEY) ?? '1.0'),
  )
  const volumeRef = useRef(volume)

  const [outputDevices, setOutputDevices] = useState<MediaDeviceInfo[]>([])
  const [outputDeviceId, setOutputDeviceIdState] = useState<string | null>(() =>
    localStorage.getItem(TTS_OUTPUT_DEVICE_KEY),
  )
  const outputDeviceIdRef = useRef(outputDeviceId)

  const [ttsEnabled, setTtsEnabledState] = useState<boolean>(
    () => localStorage.getItem(TTS_ENABLED_KEY) === 'true',
  )
  const ttsEnabledRef = useRef(ttsEnabled)

  const [ttsEngine, setTtsEngine] = useState<string>('local')
  const ttsEngineRef = useRef(ttsEngine)

  const streamTextRef = useRef('')
  const streamSynthesizedRef = useRef(0)
  const streamIsFinalRef = useRef(false)
  const streamProcessingRef = useRef(false)
  const stopGenerationRef = useRef(0)
  const playbackQueueRef = useRef<Blob[]>([])
  const isPlayingQueueRef = useRef(false)

  useEffect(() => {
    if (!navigator.mediaDevices?.enumerateDevices) return
    navigator.mediaDevices
      .enumerateDevices()
      .then((devices) => {
        setOutputDevices(devices.filter((d) => d.kind === 'audiooutput'))
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    sidecarFetch('/api/voice/settings')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.tts_engine) {
          setTtsEngine(data.tts_engine)
          ttsEngineRef.current = data.tts_engine
        }
      })
      .catch(() => {})
  }, [])

  const playBlob = useCallback(async (blob: Blob): Promise<void> => {
    return new Promise<void>((resolve, reject) => {
      const url = URL.createObjectURL(blob)
      const audio = audioRef.current ?? new Audio()
      audioRef.current = audio
      audio.src = url
      audio.volume = volumeRef.current

      if (outputDeviceIdRef.current) {
        void applySinkId(audio, outputDeviceIdRef.current)
      }

      audio.onended = () => {
        URL.revokeObjectURL(url)
        resolve()
      }
      audio.onerror = () => {
        URL.revokeObjectURL(url)
        reject(new Error('playback error'))
      }

      setIsSpeaking(true)
      audio.play().catch(reject)
    })
  }, [])

  const playQueue = useCallback(async (): Promise<void> => {
    if (isPlayingQueueRef.current) return
    isPlayingQueueRef.current = true
    setIsSpeaking(true)
    try {
      while (playbackQueueRef.current.length > 0) {
        const blob = playbackQueueRef.current.shift()!
        try {
          await playBlob(blob)
        } catch (err) {
          if (import.meta.env.DEV) console.error('[TTS] chunk playback failed:', err)
        }
      }
    } finally {
      isPlayingQueueRef.current = false
      setIsSpeaking(false)
    }
  }, [playBlob])

  const synthesizeChunk = useCallback(async (text: string): Promise<Blob | null> => {
    const clean = stripMarkdown(text).trim()
    if (!clean) return null
    try {
      const response = await sidecarFetch('/api/voice/synthesize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: clean }),
      })
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
      const blob = await response.blob()
      if (import.meta.env.DEV) {
        console.log('[TTS] chunk synthesized:', clean.slice(0, 80), 'bytes:', blob.size)
      }
      return blob
    } catch (err) {
      if (import.meta.env.DEV) console.error('[TTS] chunk synthesize failed:', err)
      return null
    }
  }, [])

  const enqueueBlob = useCallback(
    (blob: Blob) => {
      playbackQueueRef.current.push(blob)
      void playQueue()
    },
    [playQueue],
  )

  const speakStreaming = useCallback(
    async (text: string, isFinal: boolean): Promise<void> => {
      if (!ttsEnabledRef.current) return

      streamTextRef.current = text
      streamIsFinalRef.current = isFinal

      if (streamProcessingRef.current) return
      streamProcessingRef.current = true

      const myGeneration = stopGenerationRef.current

      try {
        while (true) {
          if (myGeneration !== stopGenerationRef.current) return

          const currentText = streamTextRef.current
          const start = streamSynthesizedRef.current
          const final = streamIsFinalRef.current

          if (currentText.length <= start) {
            if (final) {
              streamSynthesizedRef.current = currentText.length
            }
            break
          }

          const newPortion = currentText.slice(start)

          if (final) {
            if (newPortion.trim()) {
              const blob = await synthesizeChunk(newPortion)
              if (blob && myGeneration === stopGenerationRef.current) {
                enqueueBlob(blob)
              }
            }
            streamSynthesizedRef.current = currentText.length
            break
          }

          const bp = findBreakpoint(newPortion, newPortion.length)
          if (bp <= 0) break

          const chunk = newPortion.slice(0, bp)
          const blob = await synthesizeChunk(chunk)
          if (blob && myGeneration === stopGenerationRef.current) {
            enqueueBlob(blob)
          }
          streamSynthesizedRef.current = start + bp
        }
      } finally {
        streamProcessingRef.current = false
      }
    },
    [synthesizeChunk, enqueueBlob],
  )

  const flushStream = useCallback(async (): Promise<void> => {
    const text = streamTextRef.current
    const start = streamSynthesizedRef.current
    const remaining = text.slice(start)
    if (remaining.trim()) {
      const blob = await synthesizeChunk(remaining)
      if (blob) enqueueBlob(blob)
    }
    streamSynthesizedRef.current = text.length
  }, [synthesizeChunk, enqueueBlob])

  const resetStream = useCallback((): void => {
    stopGenerationRef.current++
    streamTextRef.current = ''
    streamSynthesizedRef.current = 0
    streamIsFinalRef.current = false
    streamProcessingRef.current = false
    playbackQueueRef.current = []
    isPlayingQueueRef.current = false
  }, [])

  const speak = useCallback(
    async (text: string): Promise<void> => {
      if (!ttsEnabledRef.current) return

      resetStream()
      audioRef.current?.pause()
      audioRef.current = null

      const myGeneration = stopGenerationRef.current

      if (import.meta.env.DEV) console.log('[TTS] speak request:', text.slice(0, 100))

      const endpoint = ttsEngineRef.current === 'cloud'
        ? '/api/voice/synthesize-stream'
        : '/api/voice/synthesize'

      try {
        const response = await sidecarFetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text }),
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }

        const blob = await response.blob()

        if (import.meta.env.DEV)
          console.log('[TTS] speak response:', blob.size, 'bytes, type:', blob.type)

        if (myGeneration === stopGenerationRef.current) {
          enqueueBlob(blob)
        }
      } catch (err) {
        if (import.meta.env.DEV) console.error('[TTS] speak failed:', err)
        setIsSpeaking(false)
      }
    },
    [resetStream, enqueueBlob],
  )

  const stop = useCallback((): void => {
    stopGenerationRef.current++
    audioRef.current?.pause()
    audioRef.current = null
    playbackQueueRef.current = []
    isPlayingQueueRef.current = false
    streamTextRef.current = ''
    streamSynthesizedRef.current = 0
    streamIsFinalRef.current = false
    streamProcessingRef.current = false
    setIsSpeaking(false)
  }, [])

  const setVolume = useCallback((v: number): void => {
    setVolumeState(v)
    volumeRef.current = v
    try {
      localStorage.setItem(TTS_VOLUME_KEY, String(v))
    } catch {
      // localStorage not available
    }
    if (audioRef.current) {
      audioRef.current.volume = v
    }
  }, [])

  const testChime = useCallback(async (): Promise<void> => {
    if (import.meta.env.DEV) console.log('[TTS] chime at volume:', volumeRef.current)

    const myGeneration = stopGenerationRef.current

    try {
      const response = await sidecarFetch('/api/voice/chime', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ volume: volumeRef.current }),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const blob = await response.blob()
      if (myGeneration === stopGenerationRef.current) {
        await playBlob(blob)
      }
    } catch (err) {
      if (import.meta.env.DEV) console.error('[TTS] chime failed:', err)
      setIsSpeaking(false)
    }
  }, [playBlob])

  const setOutputDeviceId = useCallback((id: string | null): void => {
    setOutputDeviceIdState(id)
    outputDeviceIdRef.current = id
    try {
      if (id !== null) {
        localStorage.setItem(TTS_OUTPUT_DEVICE_KEY, id)
      } else {
        localStorage.removeItem(TTS_OUTPUT_DEVICE_KEY)
      }
    } catch {
      // localStorage not available
    }
    if (import.meta.env.DEV) console.log('[TTS] output device:', id)
    if (audioRef.current) {
      void applySinkId(audioRef.current, id ?? '')
    }
  }, [])

  const setTtsEnabled = useCallback((enabled: boolean): void => {
    setTtsEnabledState(enabled)
    ttsEnabledRef.current = enabled
    try {
      localStorage.setItem(TTS_ENABLED_KEY, String(enabled))
    } catch {
      // localStorage not available
    }
  }, [])

  return {
    speak,
    speakStreaming,
    speakStream: speak,
    flushStream,
    resetStream,
    stop,
    isSpeaking,
    volume,
    setVolume,
    testChime,
    outputDevices,
    outputDeviceId,
    setOutputDeviceId,
    ttsEnabled,
    setTtsEnabled,
    ttsEngine,
  }
}
