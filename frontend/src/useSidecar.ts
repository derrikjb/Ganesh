import { useEffect, useRef, useState } from 'react'
import { checkSidecarHealth, getSidecarPort } from './api'

const RECONNECT_INTERVAL_MS = 1000
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
        const url = `http://127.0.0.1:${port}`
        if (cancelledRef.current) return
        setSidecarUrl(url)

        const healthy = await checkSidecarHealth()
        if (cancelledRef.current) return
        if (healthy) {
          setIsReady(true)
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

    void connect(1)

    return () => {
      cancelledRef.current = true
    }
  }, [])

  return { sidecarUrl, isReady, attempts }
}
