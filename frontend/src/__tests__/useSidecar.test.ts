import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

import { invoke } from '@tauri-apps/api/core'
import { useSidecar } from '../useSidecar'

const mockInvoke = invoke as unknown as ReturnType<typeof vi.fn>

function mockFetchSequence(responses: { ok: boolean }[]): void {
  const fn = vi.fn()
  responses.forEach((r) => fn.mockResolvedValueOnce(r))
  global.fetch = fn as unknown as typeof fetch
}

function mockFetchOk(ok: boolean): void {
  global.fetch = vi.fn().mockResolvedValue({ ok }) as unknown as typeof fetch
}

describe('useSidecar', () => {
  beforeEach(() => {
    vi.useRealTimers()
    mockInvoke.mockReset()
    mockFetchOk(true)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('becomes ready when port is returned and /health succeeds', async () => {
    mockInvoke.mockResolvedValue(4242)
    mockFetchOk(true)

    const { result } = renderHook(() => useSidecar())

    await waitFor(() => expect(result.current.isReady).toBe(true), { timeout: 3000 })
    expect(result.current.sidecarUrl).toBe('http://127.0.0.1:4242')
    expect(mockInvoke).toHaveBeenCalledWith('get_sidecar_port')
    expect(global.fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:4242/health',
      undefined,
    )
  })

  it('retries when /health fails then succeeds on a later attempt', async () => {
    mockInvoke.mockResolvedValue(5555)
    mockFetchSequence([{ ok: false }, { ok: true }])

    const { result } = renderHook(() => useSidecar())

    await waitFor(() => expect(result.current.isReady).toBe(true), { timeout: 5000 })
    expect(result.current.sidecarUrl).toBe('http://127.0.0.1:5555')
    expect(global.fetch).toHaveBeenCalledTimes(2)
  })

  it('retries when invoke throws', async () => {
    mockInvoke
      .mockRejectedValueOnce(new Error('not ready'))
      .mockResolvedValue(7777)
    mockFetchOk(true)

    const { result } = renderHook(() => useSidecar())

    await waitFor(() => expect(result.current.isReady).toBe(true), { timeout: 5000 })
    expect(result.current.sidecarUrl).toBe('http://127.0.0.1:7777')
  })

  it('stays not-ready when port is null', async () => {
    mockInvoke.mockResolvedValue(null)
    mockFetchOk(true)

    const { result } = renderHook(() => useSidecar())

    await new Promise((r) => setTimeout(r, 1500))

    expect(result.current.isReady).toBe(false)
    expect(result.current.sidecarUrl).toBeNull()
  })
})
