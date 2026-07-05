import '@testing-library/jest-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { ConversationHistory } from '../components/ConversationHistory'

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

const SAMPLE_CONVS = [
  {
    id: 'conv-1',
    title: 'Python programming',
    profile_id: null,
    created_at: '2026-07-04T10:00:00Z',
    updated_at: '2026-07-04T10:05:00Z',
    message_count: 2,
  },
  {
    id: 'conv-2',
    title: 'Weather chat',
    profile_id: null,
    created_at: '2026-07-04T11:00:00Z',
    updated_at: '2026-07-04T11:03:00Z',
    message_count: 1,
  },
]

const CONV_DETAIL = {
  id: 'conv-1',
  title: 'Python programming',
  profile_id: null,
  created_at: '2026-07-04T10:00:00Z',
  updated_at: '2026-07-04T10:05:00Z',
  messages: [
    { id: 'm1', role: 'user', content: 'Hello', created_at: '2026-07-04T10:00:00Z' },
    { id: 'm2', role: 'assistant', content: 'Hi there', created_at: '2026-07-04T10:01:00Z' },
  ],
  message_count: 2,
}

describe('ConversationHistory', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders conversations fetched from /api/conversations', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ conversations: SAMPLE_CONVS }))

    render(<ConversationHistory onSelect={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByTestId('conversation-row-conv-1')).toBeInTheDocument()
    })
    expect(screen.getByTestId('conversation-row-conv-2')).toBeInTheDocument()
    expect(screen.getByTestId('conversation-title-conv-1').textContent).toBe('Python programming')
  })

  it('shows empty state when no conversations exist', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ conversations: [] }))

    render(<ConversationHistory onSelect={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByTestId('conversation-empty')).toBeInTheDocument()
    })
  })

  it('loads conversation detail on row click and calls onSelect', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ conversations: SAMPLE_CONVS }))
    mockFetch.mockResolvedValueOnce(mockResponse(CONV_DETAIL))

    const onSelect = vi.fn()
    render(<ConversationHistory onSelect={onSelect} />)

    await waitFor(() => {
      expect(screen.getByTestId('conversation-row-conv-1')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('conversation-row-conv-1'))

    await waitFor(() => {
      expect(onSelect).toHaveBeenCalledWith(CONV_DETAIL)
    })
  })

  it('triggers semantic search on query input', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ conversations: SAMPLE_CONVS }))
    mockFetch.mockResolvedValueOnce(mockResponse({ results: [CONV_DETAIL] }))

    render(<ConversationHistory onSelect={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByTestId('conversation-row-conv-1')).toBeInTheDocument()
    })

    const input = screen.getByTestId('conversation-search-input')
    fireEvent.change(input, { target: { value: 'python' } })

    await waitFor(() => {
      const searchCall = mockFetch.mock.calls.find(
        ([path]) => typeof path === 'string' && path.includes('/api/conversations/search'),
      )
      expect(searchCall).toBeDefined()
    })
  })

  it('opens export dropdown and triggers JSON export', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ conversations: SAMPLE_CONVS }))
    mockFetch.mockResolvedValueOnce(mockResponse({ format: 'json', content: '{}' }))

    render(<ConversationHistory onSelect={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByTestId('conversation-row-conv-1')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('conversation-export-conv-1'))

    await waitFor(() => {
      expect(screen.getByTestId('conversation-export-menu-conv-1')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('conversation-export-json-conv-1'))

    await waitFor(() => {
      const exportCall = mockFetch.mock.calls.find(
        ([path, init]) =>
          path === '/api/conversations/conv-1/export' &&
          (init as RequestInit)?.method === 'POST',
      )
      expect(exportCall).toBeDefined()
    })
  })

  it('shows delete confirmation and deletes conversation', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ conversations: SAMPLE_CONVS }))
    mockFetch.mockResolvedValueOnce(mockResponse(null, { status: 204 }))

    render(<ConversationHistory onSelect={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByTestId('conversation-row-conv-1')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('conversation-delete-conv-1'))

    await waitFor(() => {
      expect(screen.getByTestId('conversation-delete-confirm')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('conversation-delete-confirm-btn'))

    await waitFor(() => {
      const deleteCall = mockFetch.mock.calls.find(
        ([path, init]) =>
          path === '/api/conversations/conv-1' &&
          (init as RequestInit)?.method === 'DELETE',
      )
      expect(deleteCall).toBeDefined()
    })

    await waitFor(() => {
      expect(screen.queryByTestId('conversation-row-conv-1')).toBeNull()
    })
  })

  it('shows error message when fetch fails', async () => {
    mockFetch.mockRejectedValueOnce(new Error('network down'))

    render(<ConversationHistory onSelect={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByTestId('conversation-error')).toBeInTheDocument()
    })
    expect(screen.getByTestId('conversation-error').textContent).toContain('network down')
  })
})
