import { useEffect, useState } from 'react'
import { sidecarFetch } from '../api'

interface WelcomePayload {
  message: string | null
  duration_seconds?: number
  duration_phrase?: string
  last_topic?: string | null
  last_task_id?: string | null
  last_session_id?: string
}

interface WelcomeBannerProps {
  onContinue?: () => void
}

export function WelcomeBanner({ onContinue }: WelcomeBannerProps) {
  const [payload, setPayload] = useState<WelcomePayload | null>(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    let cancelled = false
    sidecarFetch('/api/continuity/welcome')
      .then((res) => (res.ok ? res.json() : { message: null }))
      .then((data: WelcomePayload) => {
        if (!cancelled && data.message) {
          setPayload(data)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  if (dismissed || !payload?.message) return null

  return (
    <div
      className="flex items-center justify-between gap-4 px-4 py-3 bg-bg-secondary border-b border-border"
      data-testid="welcome-banner"
      role="status"
    >
      <p className="text-sm text-text-primary flex-1" data-testid="welcome-message">
        {payload.message}
      </p>
      <div className="flex items-center gap-2 shrink-0">
        <button
          className="px-3 py-1.5 text-sm rounded-md bg-accent-primary text-white hover:opacity-90 transition-opacity"
          data-testid="welcome-continue-button"
          onClick={() => {
            setDismissed(true)
            onContinue?.()
          }}
        >
          Continue
        </button>
        <button
          className="px-3 py-1.5 text-sm rounded-md border border-border text-text-muted hover:text-text-primary hover:bg-bg-tertiary transition-colors"
          data-testid="welcome-dismiss-button"
          onClick={() => setDismissed(true)}
        >
          Dismiss
        </button>
      </div>
    </div>
  )
}
