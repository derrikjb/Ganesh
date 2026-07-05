import { useCallback, useEffect, useState } from 'react'
import { sidecarFetch } from '../api'

export interface SubAgentTask {
  task_id: string
  goal: string
  status: string
  current_action: string
  task_type: string
  started_at: string
  completed_at?: string | null
}

interface ListResponse {
  agents: SubAgentTask[]
}

interface TaskPanelProps {
  refreshIntervalMs?: number
  onClose?: () => void
}

const ACTIVE_STATUSES = new Set(['pending', 'running'])

export function TaskPanel({
  refreshIntervalMs = 2000,
  onClose,
}: TaskPanelProps): JSX.Element {
  const [tasks, setTasks] = useState<SubAgentTask[]>([])
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [cancelling, setCancelling] = useState<Record<string, boolean>>({})

  const refresh = useCallback(async () => {
    try {
      const res = await sidecarFetch('/api/agents')
      if (!res.ok) {
        setError(`status ${res.status}`)
        return
      }
      const data = (await res.json()) as ListResponse
      setTasks(data.agents ?? [])
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

  const toggle = useCallback((id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))
  }, [])

  const handleCancel = useCallback(
    async (id: string) => {
      setCancelling((prev) => ({ ...prev, [id]: true }))
      try {
        await sidecarFetch(`/api/agents/${id}/cancel`, { method: 'POST' })
        await refresh()
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setCancelling((prev) => ({ ...prev, [id]: false }))
      }
    },
    [refresh],
  )

  return (
    <div
      className="flex flex-col h-full bg-bg-secondary border-l border-border"
      data-testid="task-panel"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold text-text-primary">
          Background Tasks
        </h2>
        <div className="flex items-center gap-2">
          <button
            onClick={() => void refresh()}
            className="text-text-muted hover:text-text-primary text-xs"
            aria-label="Refresh tasks"
            data-testid="task-refresh"
          >
            ↻
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="text-text-muted hover:text-text-primary text-xs"
              aria-label="Close task panel"
              data-testid="task-close"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {error && (
        <div
          className="px-4 py-2 text-xs text-status-error bg-status-error/10"
          data-testid="task-error"
        >
          {error}
        </div>
      )}

      <div className="flex-1 overflow-y-auto" data-testid="task-list">
        {tasks.length === 0 ? (
          <div
            className="px-4 py-6 text-xs text-text-muted text-center"
            data-testid="task-empty"
          >
            No active background tasks
          </div>
        ) : (
          tasks.map((task) => {
            const isExpanded = expanded[task.task_id] ?? false
            const isActive = ACTIVE_STATUSES.has(task.status)
            return (
              <div
                key={task.task_id}
                className="border-b border-border px-4 py-3"
                data-testid={`task-row-${task.task_id}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <button
                    onClick={() => toggle(task.task_id)}
                    className="flex-1 text-left"
                    data-testid={`task-toggle-${task.task_id}`}
                    aria-expanded={isExpanded}
                  >
                    <div
                      className="text-xs font-medium text-text-primary truncate"
                      data-testid={`task-goal-${task.task_id}`}
                    >
                      {task.goal}
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded ${
                          task.status === 'running'
                            ? 'bg-status-success/20 text-status-success'
                            : task.status === 'pending'
                              ? 'bg-status-warning/20 text-status-warning'
                              : 'bg-bg-tertiary text-text-muted'
                        }`}
                        data-testid={`task-status-${task.task_id}`}
                      >
                        {task.status}
                      </span>
                      <span
                        className="text-[10px] text-text-muted"
                        data-testid={`task-type-${task.task_id}`}
                      >
                        {task.task_type}
                      </span>
                    </div>
                  </button>
                  {isActive && (
                    <button
                      onClick={() => void handleCancel(task.task_id)}
                      disabled={cancelling[task.task_id] ?? false}
                      className="text-[10px] text-status-error hover:text-status-error/80 disabled:opacity-50 px-2 py-0.5 rounded border border-status-error/40"
                      data-testid={`task-cancel-${task.task_id}`}
                      aria-label={`Cancel task ${task.task_id}`}
                    >
                      {cancelling[task.task_id] ? '…' : 'Cancel'}
                    </button>
                  )}
                </div>

                {isExpanded && (
                  <div
                    className="mt-2 text-[11px] text-text-secondary space-y-1"
                    data-testid={`task-details-${task.task_id}`}
                  >
                    <div>
                      <span className="text-text-muted">id:</span>{' '}
                      <span data-testid={`task-id-${task.task_id}`}>
                        {task.task_id}
                      </span>
                    </div>
                    <div>
                      <span className="text-text-muted">action:</span>{' '}
                      {task.current_action || '—'}
                    </div>
                    <div>
                      <span className="text-text-muted">started:</span>{' '}
                      {task.started_at}
                    </div>
                    {task.completed_at && (
                      <div>
                        <span className="text-text-muted">completed:</span>{' '}
                        {task.completed_at}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
