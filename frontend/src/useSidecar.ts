import { useCallback, useEffect, useRef, useState } from 'react'
import { checkSidecarHealth, getSidecarPort } from './api'

const RECONNECT_INTERVAL_MS = 1000
const HEALTH_CHECK_INTERVAL_MS = 2000
const MAX_RECONNECT_ATTEMPTS = 30
const POST_CRASH_MAX_RETRIES = 3
const POST_CRASH_RETRY_INTERVAL_MS = 2000

export type SidecarState = 'connecting' | 'ready' | 'reconnecting' | 'offline'

export interface SidecarOptions {
  reconnectIntervalMs?: number
  healthCheckIntervalMs?: number
  maxReconnectAttempts?: number
  postCrashMaxRetries?: number
  postCrashRetryIntervalMs?: number
}

export interface SidecarStatus {
  sidecarUrl: string | null
  isReady: boolean
  attempts: number
  status: SidecarState
  restartSidecar: () => void
}

export function useSidecar(options: SidecarOptions = {}): SidecarStatus {
  const {
    reconnectIntervalMs = RECONNECT_INTERVAL_MS,
    healthCheckIntervalMs = HEALTH_CHECK_INTERVAL_MS,
    maxReconnectAttempts = MAX_RECONNECT_ATTEMPTS,
    postCrashMaxRetries = POST_CRASH_MAX_RETRIES,
    postCrashRetryIntervalMs = POST_CRASH_RETRY_INTERVAL_MS,
  } = options

  const [sidecarUrl, setSidecarUrl] = useState<string | null>(null)
  const [isReady, setIsReady] = useState(false)
  const [attempts, setAttempts] = useState(0)
  const [status, setStatus] = useState<SidecarState>('connecting')
  const cancelledRef = useRef(false)
  const readyRef = useRef(false)
  const portRef = useRef<number | null>(null)
  const postCrashRetriesRef = useRef(0)
  const restartTriggerRef = useRef(0)
  const [restartTrigger, setRestartTrigger] = useState(0)

  const restartSidecar = useCallback(() => {
    postCrashRetriesRef.current = 0
    restartTriggerRef.current += 1
    setRestartTrigger(restartTriggerRef.current)
  }, [])

  useEffect(() => {
    cancelledRef.current = false
    readyRef.current = false
    postCrashRetriesRef.current = 0
    setStatus('connecting')
    setIsReady(false)

    async function connect(attempt: number): Promise<void> {
      if (cancelledRef.current) return
      setAttempts(attempt)
      setStatus('connecting')

      try {
        const port = await getSidecarPort()
        if (cancelledRef.current) return
        if (port === undefined || port === null) {
          scheduleRetry(attempt)
          return
        }
        portRef.current = port
        const url = `http://127.0.0.1:${port}`
        if (cancelledRef.current) return
        setSidecarUrl(url)

        const healthy = await checkSidecarHealth()
        if (cancelledRef.current) return
        if (healthy) {
          readyRef.current = true
          setIsReady(true)
          setStatus('ready')
          startHealthMonitor()
          return
        }
        scheduleRetry(attempt)
      } catch {
        if (!cancelledRef.current) scheduleRetry(attempt)
      }
    }

    function scheduleRetry(attempt: number): void {
      if (cancelledRef.current) return
      if (attempt >= maxReconnectAttempts) {
        setStatus('offline')
        return
      }
      const next = attempt + 1
      setTimeout(() => void connect(next), reconnectIntervalMs)
    }

    let monitorTimer: ReturnType<typeof setTimeout> | null = null
    function startHealthMonitor(): void {
      if (monitorTimer !== null) clearTimeout(monitorTimer)
      monitorTimer = setTimeout(async () => {
        if (cancelledRef.current || !readyRef.current) return
        try {
          const healthy = await checkSidecarHealth()
          if (cancelledRef.current) return
          if (!healthy) {
            handleSidecarDeath()
          } else {
            startHealthMonitor()
          }
        } catch {
          if (cancelledRef.current || !readyRef.current) return
          handleSidecarDeath()
        }
      }, healthCheckIntervalMs)
    }

    function handleSidecarDeath(): void {
      readyRef.current = false
      setIsReady(false)
      setStatus('reconnecting')
      postCrashRetriesRef.current = 0
      attemptPostCrashReconnect()
    }

    function attemptPostCrashReconnect(): void {
      if (cancelledRef.current) return
      const retryNum = postCrashRetriesRef.current + 1
      if (retryNum > postCrashMaxRetries) {
        setStatus('offline')
        return
      }
      postCrashRetriesRef.current = retryNum
      setAttempts(retryNum)
      setTimeout(async () => {
        if (cancelledRef.current) return
        try {
          const healthy = await checkSidecarHealth()
          if (cancelledRef.current) return
          if (healthy) {
            readyRef.current = true
            setIsReady(true)
            setStatus('ready')
            postCrashRetriesRef.current = 0
            startHealthMonitor()
          } else {
            attemptPostCrashReconnect()
          }
        } catch {
          if (!cancelledRef.current) attemptPostCrashReconnect()
        }
      }, postCrashRetryIntervalMs)
    }

    void connect(1)

    return () => {
      cancelledRef.current = true
      if (monitorTimer !== null) clearTimeout(monitorTimer)
    }
  }, [
    restartTrigger,
    reconnectIntervalMs,
    healthCheckIntervalMs,
    maxReconnectAttempts,
    postCrashMaxRetries,
    postCrashRetryIntervalMs,
  ])

  return { sidecarUrl, isReady, attempts, status, restartSidecar }
}
