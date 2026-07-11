import { useCallback, useEffect, useRef, useState } from 'react'
import { sidecarFetch } from '../api'
import type { UseTTSReturn } from '../types/chat'

export type { UseTTSReturn } from '../types/chat'

const TTS_ENABLED_KEY = 'ganesh_tts_enabled'
const TTS_VOLUME_KEY = 'ganesh_tts_volume'
const TTS_OUTPUT_DEVICE_KEY = 'ganesh_tts_output_device'

/**
 * Apply an audio output device to an HTMLAudioElement via setSinkId.
 * Wrapped in try/catch since not all browsers support this API.
 */
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

  useEffect(() => {
    if (!navigator.mediaDevices?.enumerateDevices) return
    navigator.mediaDevices
      .enumerateDevices()
      .then((devices) => {
        setOutputDevices(devices.filter((d) => d.kind === 'audiooutput'))
      })
      .catch(() => {})
  }, [])

  const playBlob = useCallback(async (blob: Blob): Promise<void> => {
    const url = URL.createObjectURL(blob)
    const audio = audioRef.current ?? new Audio()
    audioRef.current = audio
    audio.src = url
    audio.volume = volumeRef.current

    if (outputDeviceIdRef.current) {
      await applySinkId(audio, outputDeviceIdRef.current)
    }

    audio.onended = () => {
      URL.revokeObjectURL(url)
      setIsSpeaking(false)
      audioRef.current = null
    }
    audio.onerror = () => {
      URL.revokeObjectURL(url)
      setIsSpeaking(false)
      audioRef.current = null
      if (import.meta.env.DEV) console.error('[TTS] audio playback error')
    }

    setIsSpeaking(true)
    try {
      await audio.play()
    } catch (err) {
      URL.revokeObjectURL(url)
      setIsSpeaking(false)
      audioRef.current = null
      if (import.meta.env.DEV) console.error('[TTS] play() failed:', err)
    }
  }, [])

  const speak = useCallback(
    async (text: string): Promise<void> => {
      if (!ttsEnabledRef.current) return

      if (import.meta.env.DEV) console.log('[TTS] speak request:', text.slice(0, 100))

      try {
        const response = await sidecarFetch('/api/voice/synthesize', {
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

        await playBlob(blob)
      } catch (err) {
        if (import.meta.env.DEV) console.error('[TTS] speak failed:', err)
        setIsSpeaking(false)
      }
    },
    [playBlob],
  )

  const stop = useCallback((): void => {
    audioRef.current?.pause()
    audioRef.current = null
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
      await playBlob(blob)
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
  }
}
