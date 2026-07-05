import { useCallback, useEffect, useState } from 'react'
import { sidecarFetch } from '../api'

export interface PersonalityTraits {
  formality: number
  verbosity: number
  warmth: number
  humor: number
  assertiveness: number
}

interface PersonalityPayload {
  traits: PersonalityTraits
  baseline: PersonalityTraits
  locked: string[]
}

interface PersonalityPanelProps {
  refreshIntervalMs?: number
  onClose?: () => void
}

const TRAIT_META: Record<
  keyof PersonalityTraits,
  { label: string; min: number; max: number; lowLabel: string; highLabel: string }
> = {
  formality: { label: 'Formality', min: -1, max: 1, lowLabel: 'Casual', highLabel: 'Formal' },
  verbosity: { label: 'Verbosity', min: -1, max: 1, lowLabel: 'Concise', highLabel: 'Verbose' },
  warmth: { label: 'Warmth', min: 0, max: 1, lowLabel: 'Cold', highLabel: 'Warm' },
  humor: { label: 'Humor', min: 0, max: 1, lowLabel: 'Serious', highLabel: 'Playful' },
  assertiveness: {
    label: 'Assertiveness',
    min: -1,
    max: 1,
    lowLabel: 'Deferential',
    highLabel: 'Assertive',
  },
}

const TRAIT_KEYS = Object.keys(TRAIT_META) as (keyof PersonalityTraits)[]

function isLocked(locked: string[], trait: string): boolean {
  return locked.includes(trait)
}

function formatValue(value: number): string {
  return value.toFixed(2)
}

export function PersonalityPanel({
  refreshIntervalMs = 5000,
  onClose,
}: PersonalityPanelProps): JSX.Element {
  const [traits, setTraits] = useState<PersonalityTraits | null>(null)
  const [baseline, setBaseline] = useState<PersonalityTraits | null>(null)
  const [locked, setLocked] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState<Record<string, boolean>>({})

  const refresh = useCallback(async () => {
    try {
      const res = await sidecarFetch('/api/personality/traits')
      if (!res.ok) {
        setError(`status ${res.status}`)
        return
      }
      const data = (await res.json()) as PersonalityPayload
      setTraits(data.traits)
      setBaseline(data.baseline)
      setLocked(data.locked ?? [])
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [])

  useEffect(() => {
    void refresh()
    const id = window.setInterval(() => void refresh(), refreshIntervalMs)
    return () => window.clearInterval(id)
  }, [refresh, refreshIntervalMs])

  const updateTrait = useCallback(
    async (trait: keyof PersonalityTraits, value: number) => {
      if (!traits) return
      const next: PersonalityTraits = { ...traits, [trait]: value }
      setTraits(next)
      setSaving((prev) => ({ ...prev, [trait]: true }))
      try {
        const res = await sidecarFetch('/api/personality/traits', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ traits: { [trait]: value } }),
        })
        if (!res.ok) {
          setError(`status ${res.status}`)
          await refresh()
        } else {
          const data = (await res.json()) as PersonalityPayload
          setTraits(data.traits)
          setBaseline(data.baseline)
          setLocked(data.locked ?? [])
          setError(null)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
        await refresh()
      } finally {
        setSaving((prev) => ({ ...prev, [trait]: false }))
      }
    },
    [refresh, traits],
  )

  const toggleLock = useCallback(
    async (trait: keyof PersonalityTraits) => {
      const isCurrentlyLocked = isLocked(locked, trait)
      const endpoint = isCurrentlyLocked ? 'unlock' : 'lock'
      setSaving((prev) => ({ ...prev, [`lock-${trait}`]: true }))
      try {
        const res = await sidecarFetch(`/api/personality/${endpoint}/${trait}`, {
          method: 'POST',
        })
        if (!res.ok) {
          setError(`status ${res.status}`)
        } else {
          const data = (await res.json()) as PersonalityPayload
          setLocked(data.locked ?? [])
          setError(null)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setSaving((prev) => ({ ...prev, [`lock-${trait}`]: false }))
      }
    },
    [locked],
  )

  const handleReset = useCallback(async () => {
    setSaving((prev) => ({ ...prev, reset: true }))
    try {
      const res = await sidecarFetch('/api/personality/reset', { method: 'POST' })
      if (!res.ok) {
        setError(`status ${res.status}`)
      } else {
        const data = (await res.json()) as PersonalityPayload
        setTraits(data.traits)
        setBaseline(data.baseline)
        setLocked(data.locked ?? [])
        setError(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSaving((prev) => ({ ...prev, reset: false }))
    }
  }, [])

  return (
    <div
      className="flex flex-col gap-3 p-4 bg-bg-secondary rounded-lg border border-border max-w-md"
      data-testid="personality-panel"
      role="dialog"
      aria-label="Personality settings"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-text-primary">Personality</h2>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void refresh()}
            className="text-text-muted hover:text-text-primary text-xs"
            aria-label="Refresh personality"
            data-testid="personality-refresh"
          >
            ↻
          </button>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="text-text-muted hover:text-text-primary text-sm"
              aria-label="Close personality settings"
              data-testid="personality-close"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {error && (
        <div
          className="px-3 py-2 text-xs text-status-error bg-status-error/10 rounded"
          data-testid="personality-error"
        >
          {error}
        </div>
      )}

      {!traits && !error && (
        <div className="text-xs text-text-muted" data-testid="personality-loading">
          Loading…
        </div>
      )}

      {traits && baseline && (
        <div className="flex flex-col gap-4" data-testid="personality-traits">
          {TRAIT_KEYS.map((trait) => {
            const meta = TRAIT_META[trait]
            const value = traits[trait]
            const baseValue = baseline[trait]
            const lockedFlag = isLocked(locked, trait)
            const step = 0.05
            return (
              <div key={trait} className="flex flex-col gap-1" data-testid={`trait-${trait}`}>
                <div className="flex items-center justify-between">
                  <label
                    htmlFor={`slider-${trait}`}
                    className="text-sm font-medium text-text-primary"
                  >
                    {meta.label}
                  </label>
                  <div className="flex items-center gap-2">
                    <span
                      className="text-xs text-text-muted"
                      data-testid={`trait-${trait}-baseline`}
                    >
                      baseline: {formatValue(baseValue)}
                    </span>
                    <span
                      className="text-xs font-mono text-text-primary"
                      data-testid={`trait-${trait}-value`}
                    >
                      {formatValue(value)}
                    </span>
                    <button
                      type="button"
                      onClick={() => void toggleLock(trait)}
                      disabled={saving[`lock-${trait}`] ?? false}
                      className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
                        lockedFlag
                          ? 'bg-accent/20 border-accent text-accent'
                          : 'bg-bg-tertiary border-border text-text-muted hover:text-text-primary'
                      }`}
                      aria-pressed={lockedFlag}
                      aria-label={`${lockedFlag ? 'Unlock' : 'Lock'} ${meta.label}`}
                      data-testid={`trait-${trait}-lock`}
                    >
                      {lockedFlag ? '🔒' : '🔓'}
                    </button>
                  </div>
                </div>
                <input
                  id={`slider-${trait}`}
                  type="range"
                  min={meta.min}
                  max={meta.max}
                  step={step}
                  value={value}
                  disabled={lockedFlag || (saving[trait] ?? false)}
                  onChange={(e) => {
                    const v = parseFloat(e.target.value)
                    void updateTrait(trait, v)
                  }}
                  className="w-full accent-accent"
                  data-testid={`slider-${trait}`}
                  aria-valuemin={meta.min}
                  aria-valuemax={meta.max}
                  aria-valuenow={value}
                />
                <div className="flex items-center justify-between text-[10px] text-text-muted">
                  <span>{meta.lowLabel}</span>
                  <span>{meta.highLabel}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      <button
        type="button"
        onClick={() => void handleReset()}
        disabled={saving.reset ?? false}
        className="mt-2 self-start text-xs text-text-muted hover:text-text-primary disabled:opacity-50"
        data-testid="personality-reset"
      >
        {saving.reset ? 'Resetting…' : 'Reset to baseline'}
      </button>
    </div>
  )
}
