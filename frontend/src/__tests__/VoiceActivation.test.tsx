import '@testing-library/jest-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { VoiceActivation } from '../components/VoiceActivation'

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

const mockGetUserMedia = vi.fn()

function fakeStream(): unknown {
  return {
    getTracks: () => [{ stop: vi.fn() }],
  }
}

class FakeMediaRecorder {
  stream: unknown
  state = 'inactive'
  mimeType = 'audio/webm'
  ondataavailable: ((e: { data: { size: number } }) => void) | null = null
  onstop: (() => void) | null = null
  constructor(stream: unknown) {
    this.stream = stream
  }
  start(): void {
    this.state = 'recording'
  }
  stop(): void {
    this.state = 'inactive'
    this.onstop?.()
  }
}

class FakeAudioContext {
  destination = {}
  createMediaStreamSource(): { connect: () => void } {
    return { connect: () => undefined }
  }
  createScriptProcessor(): {
    connect: () => void
    onaudioprocess: ((e: unknown) => void) | null
  } {
    return { connect: () => undefined, onaudioprocess: null }
  }
  close(): Promise<void> {
    return Promise.resolve()
  }
}

function setupMediaStream(): void {
  Object.defineProperty(navigator, 'mediaDevices', {
    value: {
      getUserMedia: mockGetUserMedia,
    },
    configurable: true,
  })
  ;(globalThis as { MediaRecorder?: unknown }).MediaRecorder = FakeMediaRecorder
  ;(globalThis as { AudioContext?: unknown }).AudioContext = FakeAudioContext
}

describe('VoiceActivation', () => {
  beforeEach(() => {
    mockFetch.mockReset()
    mockGetUserMedia.mockReset()
    setupMediaStream()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders mode selector and initial state', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ state: 'idle', mode: 'push_to_talk' }),
    )
    render(<VoiceActivation />)
    await waitFor(() => {
      expect(screen.getByTestId('voice-activation')).toBeInTheDocument()
    })
    expect(screen.getByTestId('mode-selector')).toBeInTheDocument()
    expect(screen.getByTestId('mode-push_to_talk')).toBeInTheDocument()
    expect(screen.getByTestId('mode-wake_word')).toBeInTheDocument()
    expect(screen.getByTestId('mode-vad_always_on')).toBeInTheDocument()
    expect(screen.getByTestId('push-to-talk-button')).toBeInTheDocument()
    expect(screen.getByTestId('mic-status')).toHaveTextContent('idle')
  })

  it('switches mode and posts to /api/voice/set-mode', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ state: 'idle', mode: 'push_to_talk' }),
    )
    mockGetUserMedia.mockResolvedValueOnce(fakeStream())

    render(<VoiceActivation />)
    await waitFor(() => {
      expect(screen.getByTestId('mode-push_to_talk')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('mode-wake_word'))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/voice/set-mode',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ mode: 'wake_word' }),
        }),
      )
    })
  })

  it('requests microphone permission on push-to-talk press', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ state: 'idle', mode: 'push_to_talk' }),
    )
    const stream = fakeStream()
    mockGetUserMedia.mockResolvedValueOnce(stream)

    render(<VoiceActivation />)
    await waitFor(() => {
      expect(screen.getByTestId('push-to-talk-button')).toBeInTheDocument()
    })

    fireEvent.mouseDown(screen.getByTestId('push-to-talk-button'))

    await waitFor(() => {
      expect(mockGetUserMedia).toHaveBeenCalledWith({ audio: true })
    })
    await waitFor(() => {
      expect(screen.getByTestId('mic-status')).toHaveTextContent('recording')
    })
    expect(mockFetch).toHaveBeenCalledWith('/api/voice/start-listening', {
      method: 'POST',
    })
  })

  it('shows denied status when microphone permission is rejected', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ state: 'idle', mode: 'push_to_talk' }),
    )
    mockGetUserMedia.mockRejectedValueOnce(new Error('Permission denied'))

    render(<VoiceActivation />)
    await waitFor(() => {
      expect(screen.getByTestId('push-to-talk-button')).toBeInTheDocument()
    })

    fireEvent.mouseDown(screen.getByTestId('push-to-talk-button'))

    await waitFor(() => {
      expect(screen.getByTestId('mic-status')).toHaveTextContent('denied')
    })
    expect(screen.getByTestId('voice-error')).toBeInTheDocument()
  })

  it('triggers barge-in via the barge-in button', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ state: 'speaking', mode: 'vad_always_on' }),
    )
    render(<VoiceActivation />)
    await waitFor(() => {
      expect(screen.getByTestId('voice-state')).toHaveTextContent('speaking')
    })

    fireEvent.click(screen.getByTestId('barge-in-button'))

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('/api/voice/barge-in', {
        method: 'POST',
      })
    })
  })
})
