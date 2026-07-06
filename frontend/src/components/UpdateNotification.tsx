import { useCallback, useEffect, useRef, useState } from 'react'
import {
  checkUpdate,
  downloadUpdate,
  installUpdate,
  cancelUpdate,
  onUpdateAvailable,
  onDownloadProgress,
  onDownloadComplete,
  type UpdateInfo,
  type DownloadProgress,
} from '../api/update'

type UpdateStatus =
  | 'idle'
  | 'checking'
  | 'available'
  | 'downloading'
  | 'ready'
  | 'installing'
  | 'error'

interface UpdateNotificationProps {
  autoCheckOnMount?: boolean
}

export function UpdateNotification({
  autoCheckOnMount = false,
}: UpdateNotificationProps): JSX.Element | null {
  const [status, setStatus] = useState<UpdateStatus>('idle')
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null)
  const [progress, setProgress] = useState<DownloadProgress | null>(null)
  const [error, setError] = useState<string | null>(null)
  const unlistenRefs = useRef<Array<() => void>>([])

  useEffect(() => {
    const setupListeners = async () => {
      const unlistenAvailable = await onUpdateAvailable((version) => {
        setUpdateInfo({
          available: true,
          version,
          current_version: '',
          body: null,
          date: null,
          download_url: null,
        })
        setStatus('available')
      })

      const unlistenProgress = await onDownloadProgress((p) => {
        setProgress(p)
        if (p.total && p.downloaded >= p.total) {
          setStatus('ready')
        }
      })

      const unlistenComplete = await onDownloadComplete(() => {
        setStatus('ready')
        setProgress(null)
      })

      unlistenRefs.current = [unlistenAvailable, unlistenProgress, unlistenComplete]
    }

    void setupListeners()

    return () => {
      unlistenRefs.current.forEach((fn) => fn())
      unlistenRefs.current = []
    }
  }, [])

  const handleCheck = useCallback(async () => {
    setStatus('checking')
    setError(null)
    try {
      const info = await checkUpdate()
      setUpdateInfo(info)
      if (info.available) {
        setStatus('available')
      } else {
        setStatus('idle')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStatus('error')
    }
  }, [])

  const handleDownload = useCallback(async () => {
    setStatus('downloading')
    setError(null)
    setProgress({ downloaded: 0, total: null })
    try {
      const success = await downloadUpdate()
      if (success) {
        setStatus('ready')
      } else {
        setStatus('available')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStatus('error')
    }
  }, [])

  const handleCancel = useCallback(async () => {
    try {
      await cancelUpdate()
      setStatus('available')
      setProgress(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStatus('error')
    }
  }, [])

  const handleInstall = useCallback(async () => {
    setStatus('installing')
    setError(null)
    try {
      await installUpdate()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setStatus('error')
    }
  }, [])

  const handleDismiss = useCallback(() => {
    setStatus('idle')
    setUpdateInfo(null)
    setError(null)
    setProgress(null)
  }, [])

  useEffect(() => {
    if (autoCheckOnMount) {
      void handleCheck()
    }
  }, [autoCheckOnMount, handleCheck])

  if (status === 'idle' || status === 'checking') {
    if (status === 'checking') {
      return (
        <div
          className="px-4 py-2 bg-bg-secondary border-b border-border text-sm text-text-muted"
          data-testid="update-checking"
        >
          Checking for updates…
        </div>
      )
    }
    return null
  }

  const percent = progress && progress.total
    ? Math.min(100, Math.round((progress.downloaded / progress.total) * 100))
    : 0

  return (
    <div
      className="px-4 py-3 bg-bg-secondary border-b border-border"
      data-testid="update-notification"
      role="alert"
    >
      {status === 'available' && (
        <div className="flex items-center justify-between gap-4">
          <div className="flex flex-col">
            <span className="text-sm font-medium text-text-primary">
              Update available — v{updateInfo?.version}
            </span>
            {updateInfo?.body && (
              <span className="text-xs text-text-muted mt-1 line-clamp-2">
                {updateInfo.body}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleDismiss}
              className="px-3 py-1.5 text-xs text-text-muted hover:text-text-primary"
              data-testid="update-dismiss"
            >
              Later
            </button>
            <button
              type="button"
              onClick={handleDownload}
              className="px-3 py-1.5 text-xs bg-accent text-white rounded hover:bg-accent-hover"
              data-testid="update-download-btn"
            >
              Download
            </button>
          </div>
        </div>
      )}

      {status === 'downloading' && (
        <div className="flex flex-col gap-2" data-testid="update-downloading">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-primary">
              Downloading update…
            </span>
            <button
              type="button"
              onClick={handleCancel}
              className="px-3 py-1 text-xs text-text-muted hover:text-text-primary"
              data-testid="update-cancel-btn"
            >
              Cancel
            </button>
          </div>
          <div
            className="w-full bg-bg-tertiary rounded-full h-2 overflow-hidden"
            data-testid="update-progress-bar"
          >
            <div
              className="h-full bg-accent transition-all duration-200"
              style={{ width: `${percent}%` }}
            />
          </div>
          <div className="flex items-center justify-between text-xs text-text-muted">
            <span data-testid="update-progress-text">
              {percent}%
            </span>
          </div>
        </div>
      )}

      {status === 'ready' && (
        <div className="flex items-center justify-between gap-4" data-testid="update-ready">
          <span className="text-sm font-medium text-text-primary">
            Update ready — install and restart?
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleDismiss}
              className="px-3 py-1.5 text-xs text-text-muted hover:text-text-primary"
              data-testid="update-later-btn"
            >
              Later
            </button>
            <button
              type="button"
              onClick={handleInstall}
              className="px-3 py-1.5 text-xs bg-accent text-white rounded hover:bg-accent-hover"
              data-testid="update-install-btn"
            >
              Install & Restart
            </button>
          </div>
        </div>
      )}

      {status === 'installing' && (
        <div className="text-sm text-text-primary" data-testid="update-installing">
          Installing update… The app will restart shortly.
        </div>
      )}

      {status === 'error' && (
        <div className="flex items-center justify-between gap-4" data-testid="update-error">
          <span className="text-sm text-status-error">
            {error ?? 'Update failed'}
          </span>
          <button
            type="button"
            onClick={handleDismiss}
            className="px-3 py-1.5 text-xs text-text-muted hover:text-text-primary"
            data-testid="update-error-dismiss"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  )
}

export default UpdateNotification
