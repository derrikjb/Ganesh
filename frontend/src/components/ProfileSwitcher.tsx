import { useCallback, useEffect, useState } from 'react'
import { sidecarFetch } from '../api'

export interface Profile {
  id: string
  name: string
  description: string | null
  color: string | null
  created_at: string
  updated_at: string
}

export interface BridgeGrant {
  id: string
  granting_profile_id: string
  receiving_profile_id: string
  memory_id: string
  created_at: string
}

export interface AuditEntry {
  id: number
  receiving_profile_id: string
  granting_profile_id: string
  query: string
  timestamp: string
}

interface ListProfilesResponse {
  profiles: Profile[]
  active_profile_id: string | null
}

interface ListGrantsResponse {
  grants: BridgeGrant[]
}

interface AuditResponse {
  entries: AuditEntry[]
}

interface BridgeQueryResult {
  id: string
  content: string
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

interface BridgeQueryResponse {
  query: string
  receiving_profile_id: string
  granting_profile_id: string
  results: BridgeQueryResult[]
}

interface ProfileSwitcherProps {
  refreshIntervalMs?: number
  onClose?: () => void
}

export function ProfileSwitcher({
  refreshIntervalMs = 10000,
  onClose,
}: ProfileSwitcherProps): JSX.Element {
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [activeProfileId, setActiveProfileId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<Record<string, boolean>>({})
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newColor, setNewColor] = useState('#7c3aed')
  const [grants, setGrants] = useState<BridgeGrant[]>([])
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [grantGrantingId, setGrantGrantingId] = useState('')
  const [grantReceivingId, setGrantReceivingId] = useState('')
  const [grantMemoryId, setGrantMemoryId] = useState('')
  const [queryGrantingId, setQueryGrantingId] = useState('')
  const [queryText, setQueryText] = useState('')
  const [queryResults, setQueryResults] = useState<BridgeQueryResult[]>([])

  const refresh = useCallback(async () => {
    try {
      const res = await sidecarFetch('/api/profiles')
      if (!res.ok) {
        setError(`status ${res.status}`)
        return
      }
      const data = (await res.json()) as ListProfilesResponse
      setProfiles(data.profiles ?? [])
      setActiveProfileId(data.active_profile_id ?? null)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [])

  const refreshGrants = useCallback(async () => {
    try {
      const res = await sidecarFetch('/api/profiles/bridge/grant')
      if (!res.ok) {
        return
      }
      const data = (await res.json()) as ListGrantsResponse
      setGrants(data.grants ?? [])
    } catch {
      // best-effort
    }
  }, [])

  const refreshAudit = useCallback(async () => {
    try {
      const res = await sidecarFetch('/api/profiles/bridge/audit?limit=20')
      if (!res.ok) {
        return
      }
      const data = (await res.json()) as AuditResponse
      setAudit(data.entries ?? [])
    } catch {
      // best-effort
    }
  }, [])

  useEffect(() => {
    void refresh()
    void refreshGrants()
    void refreshAudit()
    const id = window.setInterval(() => {
      void refresh()
      void refreshGrants()
      void refreshAudit()
    }, refreshIntervalMs)
    return () => window.clearInterval(id)
  }, [refresh, refreshGrants, refreshAudit, refreshIntervalMs])

  const createProfile = useCallback(async () => {
    if (!newName.trim()) return
    setBusy((p) => ({ ...p, create: true }))
    try {
      const res = await sidecarFetch('/api/profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: newName.trim(),
          description: newDesc.trim() || null,
          color: newColor,
        }),
      })
      if (!res.ok) {
        setError(`create status ${res.status}`)
      } else {
        setNewName('')
        setNewDesc('')
        await refresh()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy((p) => ({ ...p, create: false }))
    }
  }, [newName, newDesc, newColor, refresh])

  const activateProfile = useCallback(
    async (id: string) => {
      setBusy((p) => ({ ...p, [`activate-${id}`]: true }))
      try {
        const res = await sidecarFetch(`/api/profiles/${id}/activate`, {
          method: 'POST',
        })
        if (!res.ok) {
          setError(`activate status ${res.status}`)
        } else {
          await refresh()
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setBusy((p) => ({ ...p, [`activate-${id}`]: false }))
      }
    },
    [refresh],
  )

  const deleteProfile = useCallback(
    async (id: string) => {
      if (!window.confirm('Delete this profile? Its memories and bridge grants will be removed.')) {
        return
      }
      setBusy((p) => ({ ...p, [`delete-${id}`]: true }))
      try {
        const res = await sidecarFetch(`/api/profiles/${id}`, { method: 'DELETE' })
        if (!res.ok) {
          setError(`delete status ${res.status}`)
        } else {
          await refresh()
          await refreshGrants()
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setBusy((p) => ({ ...p, [`delete-${id}`]: false }))
      }
    },
    [refresh, refreshGrants],
  )

  const createGrant = useCallback(async () => {
    if (!grantGrantingId || !grantReceivingId || !grantMemoryId.trim()) return
    setBusy((p) => ({ ...p, grant: true }))
    try {
      const res = await sidecarFetch('/api/profiles/bridge/grant', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          granting_profile_id: grantGrantingId,
          receiving_profile_id: grantReceivingId,
          memory_id: grantMemoryId.trim(),
        }),
      })
      if (!res.ok) {
        setError(`grant status ${res.status}`)
      } else {
        setGrantMemoryId('')
        await refreshGrants()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy((p) => ({ ...p, grant: false }))
    }
  }, [grantGrantingId, grantReceivingId, grantMemoryId, refreshGrants])

  const revokeGrant = useCallback(
    async (id: string) => {
      setBusy((p) => ({ ...p, [`revoke-${id}`]: true }))
      try {
        const res = await sidecarFetch(`/api/profiles/bridge/grant/${id}`, {
          method: 'DELETE',
        })
        if (!res.ok) {
          setError(`revoke status ${res.status}`)
        } else {
          await refreshGrants()
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setBusy((p) => ({ ...p, [`revoke-${id}`]: false }))
      }
    },
    [refreshGrants],
  )

  const runBridgeQuery = useCallback(async () => {
    if (!activeProfileId || !queryGrantingId || !queryText.trim()) return
    setBusy((p) => ({ ...p, query: true }))
    try {
      const url =
        `/api/profiles/bridge/query?receiving_profile_id=${encodeURIComponent(
          activeProfileId,
        )}&granting_profile_id=${encodeURIComponent(queryGrantingId)}` +
        `&query=${encodeURIComponent(queryText.trim())}`
      const res = await sidecarFetch(url)
      if (!res.ok) {
        setError(`query status ${res.status}`)
      } else {
        const data = (await res.json()) as BridgeQueryResponse
        setQueryResults(data.results ?? [])
        await refreshAudit()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy((p) => ({ ...p, query: false }))
    }
  }, [activeProfileId, queryGrantingId, queryText, refreshAudit])

  const profileName = (id: string | null): string => {
    if (!id) return '—'
    const p = profiles.find((pr) => pr.id === id)
    return p ? p.name : id.slice(0, 8)
  }

  return (
    <div
      className="flex flex-col gap-4 p-4 bg-bg-secondary rounded-lg border border-border max-w-lg"
      data-testid="profile-switcher"
      role="dialog"
      aria-label="Profile switcher"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-text-primary">Profiles</h2>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              void refresh()
              void refreshGrants()
              void refreshAudit()
            }}
            className="text-text-muted hover:text-text-primary text-xs"
            aria-label="Refresh profiles"
            data-testid="profile-refresh"
          >
            ↻
          </button>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="text-text-muted hover:text-text-primary text-sm"
              aria-label="Close profile switcher"
              data-testid="profile-close"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {error && (
        <div
          className="px-3 py-2 text-xs text-status-error bg-status-error/10 rounded"
          data-testid="profile-error"
        >
          {error}
        </div>
      )}

      {/* Active profile indicator */}
      <div className="text-xs text-text-muted" data-testid="active-profile-indicator">
        Active: <span className="text-text-primary">{profileName(activeProfileId)}</span>
      </div>

      {/* Profile list */}
      <div className="flex flex-col gap-2" data-testid="profile-list">
        {profiles.length === 0 && (
          <div className="text-xs text-text-muted" data-testid="profile-empty">
            No profiles yet. Create one below.
          </div>
        )}
        {profiles.map((p) => {
          const isActive = p.id === activeProfileId
          return (
            <div
              key={p.id}
              className="flex items-center justify-between gap-2 px-3 py-2 rounded border border-border bg-bg-tertiary"
              data-testid={`profile-row-${p.id}`}
            >
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className="inline-block w-3 h-3 rounded-full shrink-0"
                  style={{ backgroundColor: p.color ?? '#7c3aed' }}
                  data-testid={`profile-color-${p.id}`}
                />
                <span className="text-sm text-text-primary truncate">{p.name}</span>
                {isActive && (
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded bg-accent/20 text-accent"
                    data-testid={`profile-active-badge-${p.id}`}
                  >
                    active
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1 shrink-0">
                {!isActive && (
                  <button
                    type="button"
                    onClick={() => void activateProfile(p.id)}
                    disabled={busy[`activate-${p.id}`] ?? false}
                    className="text-[10px] px-2 py-0.5 rounded border border-border text-text-muted hover:text-text-primary disabled:opacity-50"
                    data-testid={`profile-activate-${p.id}`}
                  >
                    {busy[`activate-${p.id}`] ? '…' : 'Activate'}
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => void deleteProfile(p.id)}
                  disabled={busy[`delete-${p.id}`] ?? false}
                  className="text-[10px] px-2 py-0.5 rounded border border-border text-status-error/70 hover:text-status-error disabled:opacity-50"
                  data-testid={`profile-delete-${p.id}`}
                >
                  {busy[`delete-${p.id}`] ? '…' : 'Delete'}
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {/* Create new profile */}
      <div className="flex flex-col gap-2 pt-2 border-t border-border" data-testid="profile-create">
        <div className="text-xs font-medium text-text-primary">New profile</div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="flex-1 px-2 py-1 text-sm rounded border border-border bg-bg-tertiary text-text-primary"
            data-testid="profile-new-name"
          />
          <input
            type="color"
            value={newColor}
            onChange={(e) => setNewColor(e.target.value)}
            className="w-8 h-8 rounded border border-border bg-bg-tertiary"
            data-testid="profile-new-color"
            aria-label="Profile color"
          />
        </div>
        <input
          type="text"
          placeholder="Description (optional)"
          value={newDesc}
          onChange={(e) => setNewDesc(e.target.value)}
          className="px-2 py-1 text-sm rounded border border-border bg-bg-tertiary text-text-primary"
          data-testid="profile-new-desc"
        />
        <button
          type="button"
          onClick={() => void createProfile()}
          disabled={!newName.trim() || (busy.create ?? false)}
          className="text-xs px-3 py-1 rounded border border-border bg-bg-tertiary text-text-primary hover:border-accent disabled:opacity-50"
          data-testid="profile-create-btn"
        >
          {busy.create ? 'Creating…' : 'Create profile'}
        </button>
      </div>

      {/* Bridge grants */}
      <div className="flex flex-col gap-2 pt-2 border-t border-border" data-testid="bridge-section">
        <div className="text-xs font-medium text-text-primary">Bridge grants</div>
        <div className="flex flex-col gap-1">
          <select
            value={grantGrantingId}
            onChange={(e) => setGrantGrantingId(e.target.value)}
            className="px-2 py-1 text-xs rounded border border-border bg-bg-tertiary text-text-primary"
            data-testid="grant-granting"
          >
            <option value="">Granting profile…</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <select
            value={grantReceivingId}
            onChange={(e) => setGrantReceivingId(e.target.value)}
            className="px-2 py-1 text-xs rounded border border-border bg-bg-tertiary text-text-primary"
            data-testid="grant-receiving"
          >
            <option value="">Receiving profile…</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Memory ID"
            value={grantMemoryId}
            onChange={(e) => setGrantMemoryId(e.target.value)}
            className="px-2 py-1 text-xs rounded border border-border bg-bg-tertiary text-text-primary"
            data-testid="grant-memory-id"
          />
          <button
            type="button"
            onClick={() => void createGrant()}
            disabled={
              !grantGrantingId ||
              !grantReceivingId ||
              !grantMemoryId.trim() ||
              (busy.grant ?? false)
            }
            className="text-xs px-3 py-1 rounded border border-border bg-bg-tertiary text-text-primary hover:border-accent disabled:opacity-50"
            data-testid="grant-create-btn"
          >
            {busy.grant ? 'Granting…' : 'Grant access'}
          </button>
        </div>

        <div className="flex flex-col gap-1" data-testid="grant-list">
          {grants.length === 0 && (
            <div className="text-[10px] text-text-muted" data-testid="grant-empty">
              No bridge grants.
            </div>
          )}
          {grants.map((g) => (
            <div
              key={g.id}
              className="flex items-center justify-between gap-2 px-2 py-1 text-[10px] rounded border border-border bg-bg-tertiary"
              data-testid={`grant-row-${g.id}`}
            >
              <span className="text-text-muted truncate">
                {profileName(g.granting_profile_id)} → {profileName(g.receiving_profile_id)}{' '}
                · {g.memory_id.slice(0, 8)}
              </span>
              <button
                type="button"
                onClick={() => void revokeGrant(g.id)}
                disabled={busy[`revoke-${g.id}`] ?? false}
                className="text-status-error/70 hover:text-status-error disabled:opacity-50"
                data-testid={`grant-revoke-${g.id}`}
              >
                {busy[`revoke-${g.id}`] ? '…' : 'revoke'}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Bridge query */}
      <div className="flex flex-col gap-2 pt-2 border-t border-border" data-testid="bridge-query">
        <div className="text-xs font-medium text-text-primary">Query across grants</div>
        <select
          value={queryGrantingId}
          onChange={(e) => setQueryGrantingId(e.target.value)}
          className="px-2 py-1 text-xs rounded border border-border bg-bg-tertiary text-text-primary"
          data-testid="query-granting"
        >
          <option value="">Query target profile…</option>
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Semantic query"
          value={queryText}
          onChange={(e) => setQueryText(e.target.value)}
          className="px-2 py-1 text-xs rounded border border-border bg-bg-tertiary text-text-primary"
          data-testid="query-text"
        />
        <button
          type="button"
          onClick={() => void runBridgeQuery()}
          disabled={!activeProfileId || !queryGrantingId || !queryText.trim() || (busy.query ?? false)}
          className="text-xs px-3 py-1 rounded border border-border bg-bg-tertiary text-text-primary hover:border-accent disabled:opacity-50"
          data-testid="query-run-btn"
        >
          {busy.query ? 'Querying…' : 'Run query'}
        </button>
        {queryResults.length > 0 && (
          <div className="flex flex-col gap-1" data-testid="query-results">
            {queryResults.map((r) => (
              <div
                key={r.id}
                className="px-2 py-1 text-[10px] rounded border border-border bg-bg-tertiary text-text-primary"
                data-testid={`query-result-${r.id}`}
              >
                {r.content}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Audit log */}
      <div className="flex flex-col gap-1 pt-2 border-t border-border" data-testid="audit-section">
        <div className="text-xs font-medium text-text-primary">Recent bridge access</div>
        {audit.length === 0 ? (
          <div className="text-[10px] text-text-muted" data-testid="audit-empty">
            No bridge access logged.
          </div>
        ) : (
          audit.map((a) => (
            <div
              key={a.id}
              className="px-2 py-1 text-[10px] rounded border border-border bg-bg-tertiary text-text-muted"
              data-testid={`audit-row-${a.id}`}
            >
              {profileName(a.receiving_profile_id)} → {profileName(a.granting_profile_id)}: “{a.query}”
            </div>
          ))
        )}
      </div>
    </div>
  )
}
