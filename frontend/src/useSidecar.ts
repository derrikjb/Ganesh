import { useEffect, useRef, useState } from 'react'
import { checkSidecarHealth, getSidecarPort } from './api'

const RECONNECT_INTERVAL_MS = 1000
const HEALTH_CHECK_INTERVAL_MS = 2000
const MAX_RECONNECT_ATTEMPTS = 30

export interface SidecarStatus {
  sidecarUrl: string | null
  isReady: boolean
  attempts: number
}

export function useSidecar(): SidecarStatus {
  const [sidecarUrl, setSidecarUrl] = useState<string | null>(null)
  const [isReady, setIsReady] = useState(false)
  const [attempts, setAttempts] = useState(0)
  const cancelledRef = useRef(false)
  const readyRef = useRef(false)
  const portRef = useRef<number | null>(null)

  useEffect(() => {
    cancelledRef.current = false

    async function connect(attempt: number): Promise<void> {
      if (cancelledRef.current) return
      setAttempts(attempt)

      try {
        const port = await getSidecarPort()
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
      if (attempt >= MAX_RECONNECT_ATTEMPTS) return
      const next = attempt + 1
      setTimeout(() => void connect(next), RECONNECT_INTERVAL_MS)
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
            readyRef.current = false
            setIsReady(false)
            setAttempts(1)
            scheduleRetry(1)
          } else {
            startHealthMonitor()
          }
        } catch {
          if (cancelledRef.current || !readyRef.current) return
          readyRef.current = false
          setIsReady(false)
          setAttempts(1)
          scheduleRetry(1)
        }
      }, HEALTH_CHECK_INTERVAL_MS)
    }

    void connect(1)

    return () => {
      cancelledRef.current = true
      if (monitorTimer !== null) clearTimeout(monitorTimer)
    }
  }, [])

  return { sidecarUrl, isReady, attempts }
}

