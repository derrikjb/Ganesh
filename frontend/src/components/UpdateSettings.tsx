import { useCallback, useEffect, useState } from 'react'
import {
  checkUpdate,
  getUpdateConfig,
  setUpdateConfig,
  type UpdateConfig as UpdateConfigType,
  type UpdateChannel,
  type UpdateInfo,
} from '../api/update'

const CHANNELS: UpdateChannel[] = ['stable', 'beta']

interface UpdateSettingsProps {
  onClose?: () => void
}

export function UpdateSettings({ onClose }: UpdateSettingsProps): JSX.Element {
  const [config, setConfig] = useState<UpdateConfigType>({
    channel: 'stable',
    auto_check: true,
  })
  const [checking, setChecking] = useState(false)
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void getUpdateConfig()
      .then(setConfig)
      .catch(() => {})
  }, [])

  const handleChannelChange = useCallback(
    async (channel: UpdateChannel) => {
      const next = { ...config, channel }
      setConfig(next)
      try {
        await setUpdateConfig(next)
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      }
    },
    [config],
  )

  const handleAutoCheckChange = useCallback(
    async (autoCheck: boolean) => {
      const next = { ...config, auto_check: autoCheck }
      setConfig(next)
      try {
        await setUpdateConfig(next)
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      }
    },
    [config],
  )

  const handleCheckNow = useCallback(async () => {
    setChecking(true)
    setError(null)
    setUpdateInfo(null)
    try {
      const info = await checkUpdate()
      setUpdateInfo(info)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setChecking(false)
    }
  }, [])

  return (
    <div
      className="flex flex-col gap-2 p-4 bg-bg-secondary rounded-lg border border-border max-w-md"
      data-testid="update-settings"
      role="dialog"
      aria-label="Update settings"
    >
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-base font-semibold text-text-primary">Updates</h2>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="text-text-muted hover:text-text-primary text-sm"
            aria-label="Close update settings"
            data-testid="close-update-settings"
          >
            ×
          </button>
        )}
      </div>

      <div className="py-3">
        <label
          htmlFor="update-channel-select"
          className="text-sm font-medium text-text-primary"
        >
          Update channel
        </label>
        <div className="flex gap-2 mt-2" role="group" aria-label="Update channel">
          {CHANNELS.map((ch) => (
            <button
              key={ch}
              type="button"
              onClick={() => void handleChannelChange(ch)}
              className={`px-3 py-1 rounded-md text-sm capitalize transition-colors ${
                config.channel === ch
                  ? 'bg-accent text-text-inverse'
                  : 'bg-bg-tertiary text-text-secondary hover:text-text-primary'
              }`}
              data-testid={`update-channel-${ch}`}
              aria-pressed={config.channel === ch}
            >
              {ch}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-start justify-between gap-4 py-3">
        <div className="flex flex-col">
          <label
            htmlFor="auto-check-toggle"
            className="text-sm font-medium text-text-primary"
          >
            Check automatically
          </label>
          <span className="text-xs text-text-secondary mt-1">
            Check for updates on launch.
          </span>
        </div>
        <button
          id="auto-check-toggle"
          type="button"
          role="switch"
          aria-checked={config.auto_check}
          onClick={() => void handleAutoCheckChange(!config.auto_check)}
          className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
            config.auto_check ? 'bg-accent' : 'bg-bg-tertiary'
          }`}
          data-testid="toggle-auto-check"
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
              config.auto_check ? 'translate-x-6' : 'translate-x-1'
            }`}
          />
        </button>
      </div>

      <div className="py-3 border-t border-border">
        <button
          type="button"
          onClick={() => void handleCheckNow()}
          disabled={checking}
          className="px-4 py-2 text-sm bg-accent text-white rounded hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed"
          data-testid="check-now-btn"
        >
          {checking ? 'Checking…' : 'Check for Updates'}
        </button>
      </div>

      {error && (
        <div
          className="text-status-error text-sm"
          data-testid="update-settings-error"
          role="alert"
        >
          {error}
        </div>
      )}

      {updateInfo && !checking && (
        <div
          className="text-sm text-text-secondary"
          data-testid="update-check-result"
        >
          {updateInfo.available
            ? `Update available: v${updateInfo.version}`
            : 'You are running the latest version.'}
        </div>
      )}

      {onClose && (
        <button
          type="button"
          onClick={onClose}
          className="mt-2 self-start text-xs text-text-muted hover:text-text-primary"
          data-testid="update-settings-done"
        >
          Done
        </button>
      )}
    </div>
  )
}

export default UpdateSettings
