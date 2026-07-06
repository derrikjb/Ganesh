import { useEffect, useRef, useState, useCallback } from 'react'

export type SpeedMultiplier = 0.5 | 1 | 2 | 'instant'

export interface NaturalPacingConfig {
  enabled: boolean
  speedMultiplier: SpeedMultiplier
}

export interface UseNaturalPacingOptions {
  config: NaturalPacingConfig
  timers?: {
    setTimeout: (fn: () => void, delay: number) => number
    clearTimeout: (id: number) => void
  }
}

export interface UseNaturalPacingReturn {
  pacedContent: string
  isThinking: boolean
  isPacing: boolean
}

const BASE_CHARS_PER_SEC = 60
const PARAGRAPH_PAUSE_MS = 300
const THINKING_DELAY_MS = 800

function getCharsPerSec(multiplier: SpeedMultiplier): number {
  if (multiplier === 'instant') return Infinity
  return BASE_CHARS_PER_SEC * multiplier
}

export function useNaturalPacing(
  rawContent: string,
  isStreaming: boolean,
  options: UseNaturalPacingOptions,
): UseNaturalPacingReturn {
  const { config, timers } = options
  const { enabled, speedMultiplier } = config

  const [pacedContent, setPacedContent] = useState('')
  const [isThinking, setIsThinking] = useState(false)
  const [isPacing, setIsPacing] = useState(false)

  const stateRef = useRef<'idle' | 'thinking' | 'pacing' | 'paused'>('idle')
  const bufferRef = useRef('')
  const pacedRef = useRef('')
  const timerRef = useRef<number | null>(null)
  const configRef = useRef(config)

  const setTimeoutFn = timers?.setTimeout ?? ((fn: () => void, delay: number) => window.setTimeout(fn, delay))
  const clearTimeoutFn = timers?.clearTimeout ?? ((id: number) => window.clearTimeout(id))

  useEffect(() => {
    configRef.current = config
  }, [config])

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeoutFn(timerRef.current)
    }
  }, [])

  if (!enabled || speedMultiplier === 'instant') {
    if (stateRef.current !== 'idle') {
      if (timerRef.current) clearTimeoutFn(timerRef.current)
      pacedRef.current += bufferRef.current
      bufferRef.current = ''
      setPacedContent(pacedRef.current)
      stateRef.current = 'idle'
      setIsThinking(false)
      setIsPacing(false)
    }
    return { pacedContent: rawContent, isThinking: false, isPacing: false }
  }

  useEffect(() => {
    if (isStreaming && stateRef.current === 'idle') {
      stateRef.current = 'thinking'
      setIsThinking(true)
      setIsPacing(false)
      bufferRef.current = ''
      pacedRef.current = ''
      setPacedContent('')

      timerRef.current = setTimeoutFn(() => {
        stateRef.current = 'pacing'
        setIsThinking(false)
        setIsPacing(true)
        releaseNext()
      }, THINKING_DELAY_MS)
    }
  }, [isStreaming])

  useEffect(() => {
    if (isStreaming) {
      const totalSeen = pacedRef.current.length + bufferRef.current.length
      if (rawContent.length > totalSeen) {
        bufferRef.current += rawContent.slice(totalSeen)
      }
    }
  }, [rawContent, isStreaming])

  useEffect(() => {
    if (!isStreaming && stateRef.current !== 'idle') {
      if (timerRef.current) clearTimeoutFn(timerRef.current)
      pacedRef.current += bufferRef.current
      bufferRef.current = ''
      setPacedContent(pacedRef.current)
      stateRef.current = 'idle'
      setIsThinking(false)
      setIsPacing(false)
    }
  }, [isStreaming])

  useEffect(() => {
    if (!enabled && stateRef.current !== 'idle') {
      if (timerRef.current) clearTimeoutFn(timerRef.current)
      pacedRef.current += bufferRef.current
      bufferRef.current = ''
      setPacedContent(pacedRef.current)
      stateRef.current = 'idle'
      setIsThinking(false)
      setIsPacing(false)
    }
  }, [enabled])

  const releaseNext = useCallback(() => {
    if (bufferRef.current.length === 0) return

    const charsPerSec = getCharsPerSec(configRef.current.speedMultiplier)
    const msPerChar = 1000 / charsPerSec
    const charsInBatch = Math.max(1, Math.round(100 / msPerChar))

    const searchWindow = bufferRef.current.slice(0, charsInBatch + 2)
    const paragraphIndex = searchWindow.indexOf('\n\n')

    let charsToRelease: number
    let pauseAfter = false

    if (paragraphIndex >= 0) {
      charsToRelease = paragraphIndex + 2
      pauseAfter = true
    } else {
      charsToRelease = Math.min(charsInBatch, bufferRef.current.length)
    }

    pacedRef.current += bufferRef.current.slice(0, charsToRelease)
    bufferRef.current = bufferRef.current.slice(charsToRelease)
    setPacedContent(pacedRef.current)

    if (pauseAfter) {
      stateRef.current = 'paused'
      setIsPacing(false)
      timerRef.current = setTimeoutFn(() => {
        stateRef.current = 'pacing'
        setIsPacing(true)
        releaseNext()
      }, PARAGRAPH_PAUSE_MS)
    } else if (bufferRef.current.length > 0) {
      timerRef.current = setTimeoutFn(releaseNext, Math.max(16, msPerChar * charsToRelease))
    }
  }, [])

  return { pacedContent, isThinking, isPacing }
}
