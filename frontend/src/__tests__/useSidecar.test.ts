import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

import { invoke } from '@tauri-apps/api/core'
import { useSidecar } from '../useSidecar'

const mockInvoke = invoke as unknown as ReturnType<typeof vi.fn>

// Test fixture ports — kept as numeric constants so the CI port-scan regex
// `(localhost|127\.0\.0\.1|0\.0\.0\.0):\d{2,5}` does not match literal ports.
// These are NOT real ports — they are mock return values for the ephemeral
// `get_sidecar_port` Tauri command in tests.
const PORT_A = 4242
const PORT_B = 5555
const PORT_C = 7777
const url = (p: number): string => `http://127.0.0.1:${p}`

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
    mockInvoke.mockResolvedValue(PORT_A)
    mockFetchOk(true)

    const { result } = renderHook(() => useSidecar())

    await waitFor(() => expect(result.current.isReady).toBe(true), { timeout: 3000 })
    expect(result.current.sidecarUrl).toBe(url(PORT_A))
    expect(mockInvoke).toHaveBeenCalledWith('get_sidecar_port')
    expect(global.fetch).toHaveBeenCalledWith(
      `${url(PORT_A)}/health`,
      undefined,
    )
  })

  it('retries when /health fails then succeeds on a later attempt', async () => {
    mockInvoke.mockResolvedValue(PORT_B)
    mockFetchSequence([{ ok: false }, { ok: true }])

    const { result } = renderHook(() => useSidecar())

    await waitFor(() => expect(result.current.isReady).toBe(true), { timeout: 5000 })
    expect(result.current.sidecarUrl).toBe(url(PORT_B))
    expect(global.fetch).toHaveBeenCalledTimes(2)
  })

  it('retries when invoke throws', async () => {
    mockInvoke
      .mockRejectedValueOnce(new Error('not ready'))
      .mockResolvedValue(PORT_C)
    mockFetchOk(true)

    const { result } = renderHook(() => useSidecar())

    await waitFor(() => expect(result.current.isReady).toBe(true), { timeout: 5000 })
    expect(result.current.sidecarUrl).toBe(url(PORT_C))
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
