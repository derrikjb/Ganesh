import { useCallback, useEffect, useRef, useState } from 'react'
import { sidecarFetch } from '../api'

export interface ModelInfo {
  name: string
  description: string
  present: boolean
  size: number
}

export interface ModelProgress {
  name: string
  downloaded: number
  total: number
  speed: number
  eta: number
  status: 'pending' | 'downloading' | 'paused' | 'verifying' | 'completed' | 'failed'
  error: string | null
}

interface ModelDownloadProps {
  onClose?: () => void
  onAllComplete?: () => void
}

function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return '0 B'
  const units = ['B', 'KiB', 'MiB', 'GiB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

function formatSpeed(bytesPerSec: number): string {
  if (!bytesPerSec || bytesPerSec <= 0) return '—'
  return `${formatBytes(bytesPerSec)}/s`
}

function formatEta(seconds: number): string {
  if (!seconds || seconds <= 0 || !isFinite(seconds)) return '—'
  if (seconds < 60) return `${Math.ceil(seconds)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.ceil(seconds % 60)
  return `${m}m ${s}s`
}

function progressPercent(p: ModelProgress): number {
  if (p.total <= 0) return 0
  return Math.min(100, Math.round((p.downloaded / p.total) * 100))
}

export function ModelDownload({ onClose, onAllComplete }: ModelDownloadProps): JSX.Element {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [progress, setProgress] = useState<Record<string, ModelProgress>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showModal, setShowModal] = useState(false)
  const eventSourceRef = useRef<EventSource | null>(null)

  const fetchStatus = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await sidecarFetch('/api/models/status')
      if (!res.ok) throw new Error(`status ${res.status}`)
      const data = await res.json()
      setModels(data.models ?? [])
      const allPresent = data.all_present === true
      if (!allPresent) {
        setShowModal(true)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setShowModal(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchStatus()
  }, [fetchStatus])

  const stopProgressStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }, [])

  useEffect(() => {
    return () => stopProgressStream()
  }, [stopProgressStream])

  const startProgressStream = useCallback(() => {
    if (eventSourceRef.current) return
    let port: number | null = null
    try {
      const portStr = localStorage.getItem('ganesh_sidecar_port')
      if (portStr) port = parseInt(portStr, 10)
    } catch {
    }
    if (!port) return
    const url = `http://127.0.0.1:${port}/api/models/progress`
    const es = new EventSource(url)
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as { models: Record<string, ModelProgress> }
        if (data.models) {
          setProgress(data.models)
          const allComplete = Object.values(data.models).every(
            (p) => p.status === 'completed'
          )
          if (allComplete) {
            void fetchStatus()
            onAllComplete?.()
          }
        }
      } catch {
      }
    }
    es.addEventListener('done', () => {
      void fetchStatus()
      onAllComplete?.()
    })
    es.onerror = () => {
      // EventSource auto-reconnects; nothing to do here.
    }
    eventSourceRef.current = es
  }, [fetchStatus, onAllComplete])

  const startDownload = useCallback(
    async (name: string) => {
      try {
        const res = await sidecarFetch('/api/models/download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name }),
        })
        if (!res.ok) throw new Error(`status ${res.status}`)
        startProgressStream()
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      }
    },
    [startProgressStream]
  )

  const pauseDownload = useCallback(async (name: string) => {
    try {
      await sidecarFetch('/api/models/pause', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
    } catch {
    }
  }, [])

  const resumeDownload = useCallback(
    async (name: string) => {
      try {
        await sidecarFetch('/api/models/resume', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name }),
        })
        startProgressStream()
      } catch {
      }
    },
    [startProgressStream]
  )

  const downloadAll = useCallback(async () => {
    const missing = models.filter((m) => !m.present).map((m) => m.name)
    for (const name of missing) {
      await startDownload(name)
    }
  }, [models, startDownload])

  const close = useCallback(() => {
    setShowModal(false)
    stopProgressStream()
    onClose?.()
  }, [onClose, stopProgressStream])

  if (!showModal) {
    return <></>
  }

  const allPresent = models.length > 0 && models.every((m) => m.present)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      data-testid="model-download-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="model-download-title"
    >
      <div className="bg-bg-secondary border border-border rounded-xl shadow-2xl w-full max-w-2xl mx-4 overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2
            id="model-download-title"
            className="text-xl font-semibold text-text-primary"
          >
            Download Required Models
          </h2>
          {allPresent && (
            <button
              onClick={close}
              className="text-text-muted hover:text-text-primary text-sm"
              data-testid="modal-close"
              aria-label="Close"
            >
              ✕
            </button>
          )}
        </div>

        <div className="px-6 py-4">
          <p className="text-sm text-text-secondary mb-4">
            Ganesh needs local models for speech-to-text, text-to-speech, and
            embeddings. These download once and are stored on your device.
          </p>

          {loading && (
            <div className="text-text-muted text-sm" data-testid="loading">
              Checking models…
            </div>
          )}

          {error && (
            <div
              className="text-status-error text-sm mb-4"
              data-testid="error-message"
              role="alert"
            >
              {error}
            </div>
          )}

          <ul className="space-y-3" data-testid="model-list">
            {models.map((m) => {
              const p = progress[m.name]
              const pct = p ? progressPercent(p) : m.present ? 100 : 0
              const status = p?.status ?? (m.present ? 'completed' : 'pending')
              return (
                <li
                  key={m.name}
                  className="bg-bg-tertiary rounded-lg p-4 border border-border-subtle"
                  data-testid={`model-row-${m.name}`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <div className="font-medium text-text-primary">{m.name}</div>
                      <div className="text-xs text-text-muted">{m.description}</div>
                    </div>
                    <StatusBadge status={status} />
                  </div>

                  <div
                    className="w-full bg-bg-primary rounded-full h-2 overflow-hidden"
                    data-testid={`progress-bar-${m.name}`}
                  >
                    <div
                      className="h-full bg-accent transition-all duration-200"
                      style={{ width: `${pct}%` }}
                    />
                  </div>

                  <div className="flex items-center justify-between mt-2 text-xs text-text-muted">
                    <span data-testid={`progress-text-${m.name}`}>
                      {p
                        ? `${formatBytes(p.downloaded)} / ${formatBytes(p.total)} (${pct}%)`
                        : m.present
                          ? 'Installed'
                          : 'Not downloaded'}
                    </span>
                    {p && p.status === 'downloading' && (
                      <span data-testid={`progress-speed-${m.name}`}>
                        {formatSpeed(p.speed)} · ETA {formatEta(p.eta)}
                      </span>
                    )}
                  </div>

                  {p?.error && (
                    <div className="text-status-error text-xs mt-2" role="alert">
                      {p.error}
                    </div>
                  )}

                  <div className="flex gap-2 mt-3">
                    {!m.present && status !== 'completed' && status !== 'downloading' && (
                      <button
                        onClick={() => void startDownload(m.name)}
                        className="px-3 py-1.5 text-xs bg-accent text-white rounded hover:bg-accent-hover"
                        data-testid={`download-btn-${m.name}`}
                      >
                        Download
                      </button>
                    )}
                    {status === 'downloading' && (
                      <button
                        onClick={() => void pauseDownload(m.name)}
                        className="px-3 py-1.5 text-xs bg-bg-elevated text-text-primary rounded hover:bg-border"
                        data-testid={`pause-btn-${m.name}`}
                      >
                        Pause
                      </button>
                    )}
                    {status === 'paused' && (
                      <button
                        onClick={() => void resumeDownload(m.name)}
                        className="px-3 py-1.5 text-xs bg-accent text-white rounded hover:bg-accent-hover"
                        data-testid={`resume-btn-${m.name}`}
                      >
                        Resume
                      </button>
                    )}
                    {status === 'failed' && (
                      <button
                        onClick={() => void startDownload(m.name)}
                        className="px-3 py-1.5 text-xs bg-status-error text-white rounded hover:opacity-80"
                        data-testid={`retry-btn-${m.name}`}
                      >
                        Retry
                      </button>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        </div>

        <div className="flex items-center justify-between px-6 py-4 border-t border-border bg-bg-primary">
          <button
            onClick={downloadAll}
            disabled={loading || allPresent}
            className="px-4 py-2 text-sm bg-accent text-white rounded hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed"
            data-testid="download-all-btn"
          >
            Download All
          </button>
          <button
            onClick={close}
            disabled={!allPresent}
            className="px-4 py-2 text-sm bg-bg-elevated text-text-primary rounded hover:bg-border disabled:opacity-50 disabled:cursor-not-allowed"
            data-testid="close-btn"
          >
            {allPresent ? 'Close' : 'Downloading…'}
          </button>
        </div>
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: string }): JSX.Element {
  const map: Record<string, { label: string; cls: string }> = {
    pending: { label: 'Pending', cls: 'text-text-muted' },
    downloading: { label: 'Downloading', cls: 'text-status-info' },
    paused: { label: 'Paused', cls: 'text-status-warning' },
    verifying: { label: 'Verifying', cls: 'text-status-info' },
    completed: { label: 'Installed', cls: 'text-status-success' },
    failed: { label: 'Failed', cls: 'text-status-error' },
  }
  const entry = map[status] ?? { label: status, cls: 'text-text-muted' }
  return (
    <span className={`text-xs font-medium ${entry.cls}`} data-testid="status-badge">
      {entry.label}
    </span>
  )
}

export default ModelDownload
