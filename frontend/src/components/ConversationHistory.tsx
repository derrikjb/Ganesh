import { useCallback, useEffect, useRef, useState } from 'react'
import { sidecarFetch } from '../api'
import type {
  ConversationDetail,
  ConversationSummary,
  ExportFormat,
} from '../types/conversations'

interface ConversationHistoryProps {
  onSelect: (conversation: ConversationDetail) => void
  refreshKey?: number
}

export function ConversationHistory({ onSelect, refreshKey = 0 }: ConversationHistoryProps) {
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<ConversationDetail[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [exportOpenId, setExportOpenId] = useState<string | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const fetchConversations = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await sidecarFetch('/api/conversations')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setConversations(data.conversations ?? [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conversations')
      setConversations([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchConversations()
  }, [fetchConversations, refreshKey])

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current)
    if (!searchQuery.trim()) {
      setSearchResults(null)
      return
    }
    searchTimer.current = setTimeout(async () => {
      setLoading(true)
      setError(null)
      try {
        const res = await sidecarFetch(
          `/api/conversations/search?q=${encodeURIComponent(searchQuery)}&limit=20`,
        )
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        setSearchResults(data.results ?? [])
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Search failed')
      } finally {
        setLoading(false)
      }
    }, 300)
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current)
    }
  }, [searchQuery])

  const handleSelect = useCallback(
    async (id: string) => {
      try {
        const res = await sidecarFetch(`/api/conversations/${id}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const conv: ConversationDetail = await res.json()
        onSelect(conv)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load conversation')
      }
    },
    [onSelect],
  )

  const handleExport = useCallback(
    async (id: string, format: ExportFormat) => {
      setExportOpenId(null)
      try {
        const res = await sidecarFetch(`/api/conversations/${id}/export`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ format }),
        })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        const blob = new Blob([data.content], {
          type: format === 'json' ? 'application/json' : 'text/markdown',
        })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `conversation-${id}.${format === 'json' ? 'json' : 'md'}`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Export failed')
      }
    },
    [],
  )

  const handleDelete = useCallback(
    async (id: string) => {
      setConfirmDeleteId(null)
      try {
        const res = await sidecarFetch(`/api/conversations/${id}`, { method: 'DELETE' })
        if (!res.ok && res.status !== 404) throw new Error(`HTTP ${res.status}`)
        setConversations((prev) => prev.filter((c) => c.id !== id))
        if (searchResults) {
          setSearchResults((prev) => (prev ?? []).filter((c) => c.id !== id))
        }
        window.dispatchEvent(new CustomEvent('ganesh:conversation-deleted', { detail: { id } }))
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Delete failed')
      }
    },
    [searchResults],
  )

  const displayList: ConversationSummary[] = searchResults ?? conversations

  return (
    <div className="flex flex-col h-full" data-testid="conversation-history">
      <div className="px-3 py-3 border-b border-border">
        <h2 className="text-sm font-semibold text-text-primary mb-2">Conversations</h2>
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search conversations..."
          className="w-full px-3 py-2 text-sm bg-bg-tertiary border border-border rounded-md text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
          data-testid="conversation-search-input"
          aria-label="Search conversations"
        />
      </div>

      {error && (
        <div className="px-3 py-2 bg-status-error/10 text-status-error text-xs" data-testid="conversation-error">
          {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto" data-testid="conversation-list">
        {loading && conversations.length === 0 && (
          <div className="px-3 py-4 text-xs text-text-muted" data-testid="conversation-loading">
            Loading...
          </div>
        )}
        {!loading && displayList.length === 0 && (
          <div className="px-3 py-4 text-xs text-text-muted" data-testid="conversation-empty">
            {searchQuery ? 'No search results.' : 'No conversations yet.'}
          </div>
        )}
        {displayList.map((conv) => (
          <div
            key={conv.id}
            className="px-3 py-2 border-b border-border hover:bg-bg-tertiary cursor-pointer group"
            data-testid={`conversation-row-${conv.id}`}
            onClick={() => handleSelect(conv.id)}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="text-sm text-text-primary truncate" data-testid={`conversation-title-${conv.id}`}>
                  {conv.title}
                </div>
                <div className="text-xs text-text-muted mt-0.5">
                  {conv.message_count} message{conv.message_count === 1 ? '' : 's'}
                </div>
              </div>
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <div className="relative">
                  <button
                    className="p-1 rounded hover:bg-bg-elevated text-text-muted hover:text-text-primary"
                    aria-label="Export conversation"
                    data-testid={`conversation-export-${conv.id}`}
                    onClick={(e) => {
                      e.stopPropagation()
                      setExportOpenId(exportOpenId === conv.id ? null : conv.id)
                    }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                  </button>
                  {exportOpenId === conv.id && (
                    <div
                      className="absolute right-0 top-7 z-10 bg-bg-elevated border border-border rounded-md shadow-lg py-1 min-w-[100px]"
                      data-testid={`conversation-export-menu-${conv.id}`}
                    >
                      <button
                        className="block w-full text-left px-3 py-1.5 text-xs text-text-primary hover:bg-bg-tertiary"
                        data-testid={`conversation-export-json-${conv.id}`}
                        onClick={(e) => {
                          e.stopPropagation()
                          handleExport(conv.id, 'json')
                        }}
                      >
                        JSON
                      </button>
                      <button
                        className="block w-full text-left px-3 py-1.5 text-xs text-text-primary hover:bg-bg-tertiary"
                        data-testid={`conversation-export-md-${conv.id}`}
                        onClick={(e) => {
                          e.stopPropagation()
                          handleExport(conv.id, 'markdown')
                        }}
                      >
                        Markdown
                      </button>
                    </div>
                  )}
                </div>
                <button
                  className="p-1 rounded hover:bg-bg-elevated text-text-muted hover:text-status-error"
                  aria-label="Delete conversation"
                  data-testid={`conversation-delete-${conv.id}`}
                  onClick={(e) => {
                    e.stopPropagation()
                    setConfirmDeleteId(conv.id)
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {confirmDeleteId && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" data-testid="conversation-delete-confirm">
          <div className="bg-bg-elevated border border-border rounded-lg p-4 max-w-xs mx-4">
            <p className="text-sm text-text-primary mb-4">Delete this conversation? This cannot be undone.</p>
            <div className="flex justify-end gap-2">
              <button
                className="px-3 py-1.5 text-xs text-text-muted hover:text-text-primary rounded"
                data-testid="conversation-delete-cancel"
                onClick={() => setConfirmDeleteId(null)}
              >
                Cancel
              </button>
              <button
                className="px-3 py-1.5 text-xs bg-status-error text-white rounded hover:bg-status-error/90"
                data-testid="conversation-delete-confirm-btn"
                onClick={() => handleDelete(confirmDeleteId)}
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
