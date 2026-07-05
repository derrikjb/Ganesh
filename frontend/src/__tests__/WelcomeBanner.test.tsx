import '@testing-library/jest-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { WelcomeBanner } from '../components/WelcomeBanner'

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

describe('WelcomeBanner', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  afterEach(() => {
    cleanup()
  })

  it('renders nothing when no welcome message is returned', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse({ message: null }))
    const { container } = render(<WelcomeBanner />)
    // Let the fetch resolve.
    await new Promise((r) => setTimeout(r, 10))
    expect(container.firstChild).toBeNull()
    expect(screen.queryByTestId('welcome-banner')).not.toBeInTheDocument()
  })

  it('renders the welcome message with Continue and Dismiss buttons', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({
        message: "Welcome back! It's been 2 hours. You were working on reports. Want to continue?",
        duration_seconds: 7200,
        duration_phrase: '2 hours',
        last_topic: 'reports',
        last_task_id: 't-1',
        last_session_id: 'sess-1',
      }),
    )
    render(<WelcomeBanner />)
    const message = await screen.findByTestId('welcome-message')
    expect(message.textContent).toContain("Welcome back!")
    expect(message.textContent).toContain('reports')
    expect(screen.getByTestId('welcome-continue-button')).toBeInTheDocument()
    expect(screen.getByTestId('welcome-dismiss-button')).toBeInTheDocument()
  })

  it('hides on Dismiss click', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({
        message: "Welcome back! It's been 1 hour. You were working on x. Want to continue?",
        duration_seconds: 3600,
        duration_phrase: '1 hour',
        last_topic: 'x',
        last_task_id: null,
        last_session_id: 'sess-2',
      }),
    )
    render(<WelcomeBanner />)
    await screen.findByTestId('welcome-banner')
    fireEvent.click(screen.getByTestId('welcome-dismiss-button'))
    expect(screen.queryByTestId('welcome-banner')).not.toBeInTheDocument()
  })

  it('hides and calls onContinue when Continue is clicked', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({
        message: "Welcome back! It's been 5 minutes. You were working on y. Want to continue?",
        duration_seconds: 300,
        duration_phrase: '5 minutes',
        last_topic: 'y',
        last_task_id: null,
        last_session_id: 'sess-3',
      }),
    )
    const onContinue = vi.fn()
    render(<WelcomeBanner onContinue={onContinue} />)
    await screen.findByTestId('welcome-banner')
    fireEvent.click(screen.getByTestId('welcome-continue-button'))
    expect(onContinue).toHaveBeenCalledTimes(1)
    expect(screen.queryByTestId('welcome-banner')).not.toBeInTheDocument()
  })

  it('renders nothing on fetch error', async () => {
    mockFetch.mockRejectedValueOnce(new Error('network'))
    const { container } = render(<WelcomeBanner />)
    await new Promise((r) => setTimeout(r, 10))
    expect(container.firstChild).toBeNull()
  })
})
