import type { SidecarState } from '../useSidecar'

interface SidecarStatusBannerProps {
  status: SidecarState
  attempts: number
  onRestart: () => void
}

export function SidecarStatusBanner({ status, attempts, onRestart }: SidecarStatusBannerProps) {
  if (status === 'ready' || status === 'connecting') return null

  if (status === 'reconnecting') {
    return (
      <div
        className="px-4 py-2 bg-status-warning/10 border-b border-status-warning/30 text-xs text-status-warning flex items-center justify-between"
        data-testid="sidecar-reconnecting-banner"
        role="status"
      >
        <span className="flex items-center gap-2">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="animate-spin"
            aria-hidden="true"
          >
            <path d="M21 12a9 9 0 11-6.219-8.56" />
          </svg>
          Reconnecting… (attempt {attempts} of 3)
        </span>
      </div>
    )
  }

  if (status === 'offline') {
    return (
      <div
        className="px-4 py-2 bg-status-error/10 border-b border-status-error/30 text-xs text-status-error flex items-center justify-between"
        data-testid="sidecar-offline-banner"
        role="status"
      >
        <span className="flex items-center gap-2">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
          Assistant offline
        </span>
        <button
          onClick={onRestart}
          className="px-3 py-1 rounded-md bg-status-error/20 hover:bg-status-error/30 transition-colors font-medium"
          data-testid="sidecar-restart-button"
        >
          Restart
        </button>
      </div>
    )
  }

  return null
}
