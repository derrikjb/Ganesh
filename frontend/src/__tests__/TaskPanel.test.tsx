import '@testing-library/jest-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { TaskPanel } from '../components/TaskPanel'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('../api', () => ({
  sidecarFetch: vi.fn(),
  getSidecarPort: vi.fn(),
}))

import { sidecarFetch } from '../api'

const mockFetch = sidecarFetch as ReturnType<typeof vi.fn>

function mockResponse(body: unknown, init: { ok?: boolean; status?: number } = {}): Response {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => body,
  } as unknown as Response
}

const SAMPLE_TASKS = [
  {
    task_id: 'task-1',
    goal: 'Summarise the notes',
    status: 'running',
    current_action: 'calling LLM',
    task_type: 'research',
    started_at: '2026-07-04T10:00:00Z',
    completed_at: null,
  },
  {
    task_id: 'task-2',
    goal: 'Generate code',
    status: 'pending',
    current_action: '',
    task_type: 'coding',
    started_at: '2026-07-04T10:01:00Z',
    completed_at: null,
  },
]

describe('TaskPanel', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders tasks fetched from /api/agents', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ agents: SAMPLE_TASKS }))

    render(<TaskPanel refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('task-row-task-1')).toBeInTheDocument()
    })
    expect(screen.getByTestId('task-row-task-2')).toBeInTheDocument()
    expect(screen.getByTestId('task-goal-task-1').textContent).toBe(
      'Summarise the notes',
    )
    expect(screen.getByTestId('task-status-task-1').textContent).toBe('running')
    expect(screen.getByTestId('task-status-task-2').textContent).toBe('pending')
    expect(screen.getByTestId('task-type-task-1').textContent).toBe('research')
  })

  it('shows empty state when no active tasks', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ agents: [] }))

    render(<TaskPanel refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('task-empty')).toBeInTheDocument()
    })
  })

  it('shows cancel button for active tasks and triggers cancel on click', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ agents: SAMPLE_TASKS }))
    mockFetch.mockResolvedValueOnce(mockResponse({ cancelled: true }))
    mockFetch.mockResolvedValueOnce(mockResponse({ agents: [] }))

    render(<TaskPanel refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('task-cancel-task-1')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('task-cancel-task-1'))

    await waitFor(() => {
      const cancelCall = mockFetch.mock.calls.find(
        ([path, init]) =>
          path === '/api/agents/task-1/cancel' &&
          (init as RequestInit)?.method === 'POST',
      )
      expect(cancelCall).toBeDefined()
    })
  })

  it('expands task details on toggle click', async () => {
    mockFetch.mockResolvedValue(mockResponse({ agents: SAMPLE_TASKS }))

    render(<TaskPanel refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('task-row-task-1')).toBeInTheDocument()
    })

    expect(screen.queryByTestId('task-details-task-1')).toBeNull()

    fireEvent.click(screen.getByTestId('task-toggle-task-1'))

    await waitFor(() => {
      expect(screen.getByTestId('task-details-task-1')).toBeInTheDocument()
    })
    expect(screen.getByTestId('task-id-task-1').textContent).toBe('task-1')
  })

  it('shows error message when fetch fails', async () => {
    mockFetch.mockRejectedValueOnce(new Error('network down'))

    render(<TaskPanel refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('task-error')).toBeInTheDocument()
    })
    expect(screen.getByTestId('task-error').textContent).toContain('network down')
  })

  it('auto-refreshes on an interval', async () => {
    mockFetch.mockResolvedValue(mockResponse({ agents: SAMPLE_TASKS }))

    render(<TaskPanel refreshIntervalMs={200} />)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled()
    })
    const firstCount = mockFetch.mock.calls.length

    await waitFor(
      () => {
        expect(mockFetch.mock.calls.length).toBeGreaterThan(firstCount)
      },
      { timeout: 2000 },
    )
  })
})
