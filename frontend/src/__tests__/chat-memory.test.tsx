import '@testing-library/jest-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, cleanup } from '@testing-library/react'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('../api', () => ({
  sidecarFetch: vi.fn(),
  getSidecarPort: vi.fn(),
}))

import { sidecarFetch } from '../api'

const mockSidecarFetch = sidecarFetch as ReturnType<typeof vi.fn>

function makeSseReader(chunks: string[]) {
  const encoded = chunks.map((c) => new TextEncoder().encode(c))
  let i = 0
  return {
    read: vi.fn(async () => {
      if (i < encoded.length) {
        return { done: false, value: encoded[i++] }
      }
      return { done: true, value: undefined }
    }),
  }
}

function mockSseResponse(chunks: string[]) {
  const reader = makeSseReader(chunks)
  mockSidecarFetch.mockResolvedValue({
    ok: true,
    body: { getReader: () => reader },
  })
  return reader
}

describe('Chat memory integration', () => {
  beforeEach(() => {
    mockSidecarFetch.mockReset()
    localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('propagates conversation_id from SSE event and sends it on subsequent messages', async () => {
    const { useChat } = await import('../hooks/useChat')
    const { result } = renderHook(() => useChat())

    expect(result.current.conversationId).toBeNull()

    mockSseResponse([
      'event: conversation\ndata: {"conversation_id": "conv-from-server"}\n\n',
      'data: {"content": "Hello"}\n\n',
      'event: done\ndata: {"done": true}\n\n',
    ])

    await result.current.sendMessage('First message')

    await waitFor(() => {
      expect(result.current.conversationId).toBe('conv-from-server')
    }, { timeout: 3000 })

    mockSseResponse([
      'event: conversation\ndata: {"conversation_id": "conv-from-server"}\n\n',
      'data: {"content": "World"}\n\n',
      'event: done\ndata: {"done": true}\n\n',
    ])

    await result.current.sendMessage('Second message')

    await waitFor(() => {
      const secondCall = mockSidecarFetch.mock.calls[1]
      expect(secondCall).toBeDefined()
      const body = JSON.parse(secondCall[1].body)
      expect(body.conversation_id).toBe('conv-from-server')
    }, { timeout: 3000 })
  })

  it('sends null conversation_id on first message when no prior conversation exists', async () => {
    const { useChat } = await import('../hooks/useChat')
    const { result } = renderHook(() => useChat())

    mockSseResponse([
      'event: conversation\ndata: {"conversation_id": "new-conv-123"}\n\n',
      'event: done\ndata: {"done": true}\n\n',
    ])

    await result.current.sendMessage('Fresh start')

    await waitFor(() => {
      const firstCall = mockSidecarFetch.mock.calls[0]
      expect(firstCall).toBeDefined()
      const body = JSON.parse(firstCall[1].body)
      expect(body.conversation_id).toBeNull()
    }, { timeout: 3000 })
  })

  it('updates conversation_id when server assigns a different one mid-stream', async () => {
    const { useChat } = await import('../hooks/useChat')
    const { result } = renderHook(() => useChat())

    mockSseResponse([
      'event: conversation\ndata: {"conversation_id": "server-assigned-id"}\n\n',
      'data: {"content": "Response"}\n\n',
      'event: done\ndata: {"done": true}\n\n',
    ])

    await result.current.sendMessage('Trigger new conversation')

    await waitFor(() => {
      expect(result.current.conversationId).toBe('server-assigned-id')
    }, { timeout: 3000 })

    expect(mockSidecarFetch).toHaveBeenCalledTimes(1)
  })
})
