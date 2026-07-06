import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { renderHook, waitFor } from '@testing-library/react'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

import { invoke } from '@tauri-apps/api/core'
import { useSidecar } from '../useSidecar'
import { SidecarStatusBanner } from '../components/SidecarStatus'

const mockInvoke = invoke as unknown as ReturnType<typeof vi.fn>

function mockFetchOk(ok: boolean): void {
  global.fetch = vi.fn().mockResolvedValue({ ok }) as unknown as typeof fetch
}

function mockFetchSequence(responses: { ok: boolean }[]): void {
  const fn = vi.fn()
  responses.forEach((r) => fn.mockResolvedValueOnce(r))
  global.fetch = fn as unknown as typeof fetch
}

describe('useSidecar recovery', () => {
  beforeEach(() => {
    vi.useRealTimers()
    mockInvoke.mockReset()
    mockFetchOk(true)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('transitions to reconnecting when sidecar dies after being ready', async () => {
    mockInvoke.mockResolvedValue(4242)
    mockFetchSequence([
      { ok: true },
      { ok: true },
      { ok: false },
      { ok: false },
      { ok: false },
      { ok: false },
    ])

    const { result } = renderHook(() =>
      useSidecar({
        healthCheckIntervalMs: 100,
        postCrashRetryIntervalMs: 100,
      }),
    )

    await waitFor(() => expect(result.current.isReady).toBe(true), { timeout: 5000 })
    expect(result.current.status).toBe('ready')

    await waitFor(() => expect(result.current.status).toBe('reconnecting'), { timeout: 5000 })
    expect(result.current.isReady).toBe(false)
  }, 15000)

  it('transitions to offline after 3 failed post-crash retries', async () => {
    mockInvoke.mockResolvedValue(4242)
    mockFetchSequence([
      { ok: true },
      { ok: true },
      { ok: false },
      { ok: false },
      { ok: false },
      { ok: false },
      { ok: false },
      { ok: false },
    ])

    const { result } = renderHook(() =>
      useSidecar({
        healthCheckIntervalMs: 100,
        postCrashRetryIntervalMs: 100,
      }),
    )

    await waitFor(() => expect(result.current.isReady).toBe(true), { timeout: 5000 })
    await waitFor(() => expect(result.current.status).toBe('offline'), { timeout: 5000 })
    expect(result.current.isReady).toBe(false)
  }, 15000)

  it('recovers when sidecar comes back during reconnecting', async () => {
    mockInvoke.mockResolvedValue(4242)
    mockFetchSequence([
      { ok: true },
      { ok: true },
      { ok: true },
      { ok: true },
      { ok: false },
      { ok: true },
      { ok: true },
    ])

    const { result } = renderHook(() =>
      useSidecar({
        healthCheckIntervalMs: 100,
        postCrashRetryIntervalMs: 100,
      }),
    )

    await waitFor(() => expect(result.current.isReady).toBe(true), { timeout: 5000 })
    await waitFor(() => expect(result.current.status).toBe('reconnecting'), { timeout: 5000 })
    await waitFor(() => expect(result.current.status).toBe('ready'), { timeout: 5000 })
  }, 15000)

  it('restartSidecar triggers a new connection attempt', async () => {
    mockInvoke.mockResolvedValue(4242)
    mockFetchOk(true)

    const { result } = renderHook(() =>
      useSidecar({
        reconnectIntervalMs: 100,
      }),
    )

    await waitFor(() => expect(result.current.isReady).toBe(true), { timeout: 5000 })
    expect(result.current.status).toBe('ready')

    result.current.restartSidecar()

    await waitFor(() => expect(result.current.isReady).toBe(true), { timeout: 5000 })
  })
})

describe('SidecarStatusBanner', () => {
  afterEach(() => {
    cleanup()
  })

  it('renders nothing when status is ready', () => {
    const { container } = render(
      <SidecarStatusBanner status="ready" attempts={0} onRestart={() => {}} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when status is connecting', () => {
    const { container } = render(
      <SidecarStatusBanner status="connecting" attempts={1} onRestart={() => {}} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders reconnecting banner with attempt count', () => {
    render(
      <SidecarStatusBanner status="reconnecting" attempts={2} onRestart={() => {}} />,
    )
    const banner = screen.getByTestId('sidecar-reconnecting-banner')
    expect(banner).toBeDefined()
    expect(banner.textContent).toContain('Reconnecting')
    expect(banner.textContent).toContain('2')
  })

  it('renders offline banner with restart button', () => {
    render(
      <SidecarStatusBanner status="offline" attempts={3} onRestart={() => {}} />,
    )
    const banner = screen.getByTestId('sidecar-offline-banner')
    expect(banner).toBeDefined()
    expect(banner.textContent).toContain('offline')
    const button = screen.getByTestId('sidecar-restart-button')
    expect(button.textContent).toContain('Restart')
  })

  it('calls onRestart when restart button is clicked', async () => {
    const onRestart = vi.fn()
    render(
      <SidecarStatusBanner status="offline" attempts={3} onRestart={onRestart} />,
    )
    fireEvent.click(screen.getByTestId('sidecar-restart-button'))
    expect(onRestart).toHaveBeenCalledTimes(1)
  })
})

describe('useChat message persistence', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    localStorage.clear()
    cleanup()
  })

  it('restores messages from localStorage on mount', async () => {
    localStorage.setItem(
      'ganesh_chat_messages',
      JSON.stringify([
        {
          id: 'test-1',
          role: 'user',
          content: 'persisted message',
          timestamp: new Date().toISOString(),
          status: 'done',
        },
      ]),
    )

    const { useChat } = await import('../hooks/useChat')
    const { result } = renderHook(() => useChat())

    expect(result.current.messages.length).toBeGreaterThanOrEqual(1)
    expect(result.current.messages[0].content).toBe('persisted message')
  })
})
