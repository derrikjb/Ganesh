import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

vi.mock('../api', () => ({
  sidecarFetch: vi.fn(),
}))

import { sidecarFetch } from '../api'
import { useTTS } from '../hooks/useTTS'

const mockSidecarFetch = sidecarFetch as unknown as ReturnType<typeof vi.fn>

const MOCK_BLOB = new Blob(['fake-audio-data'], { type: 'audio/wav' })

function mockResponse(ok = true): Response {
  return {
    ok,
    status: ok ? 200 : 500,
    statusText: ok ? 'OK' : 'Internal Server Error',
    blob: vi.fn().mockResolvedValue(MOCK_BLOB),
    json: vi.fn().mockResolvedValue({ tts_engine: 'local' }),
  } as unknown as Response
}

describe('useTTS', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    mockSidecarFetch.mockReset()
    mockSidecarFetch.mockResolvedValue(mockResponse(true))

    localStorage.clear()

    vi.spyOn(HTMLAudioElement.prototype, 'play').mockImplementation(function (this: HTMLAudioElement) {
      const audio = this
      return Promise.resolve().then(() => {
        if (audio.onended) audio.onended(new Event('ended'))
      })
    })
    vi.spyOn(HTMLAudioElement.prototype, 'pause').mockImplementation(() => {})
    vi.spyOn(console, 'log').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})

    URL.createObjectURL = vi.fn().mockReturnValue('blob:mock-url')
    URL.revokeObjectURL = vi.fn().mockImplementation(() => {})

    Object.defineProperty(navigator, 'mediaDevices', {
      value: {
        enumerateDevices: vi.fn().mockResolvedValue([]),
      },
      writable: true,
      configurable: true,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('speak calls /api/voice/synthesize with correct body', async () => {
    const { result } = renderHook(() => useTTS())

    act(() => result.current.setTtsEnabled(true))

    await act(async () => {
      await result.current.speak('Hello world')
    })

    expect(mockSidecarFetch).toHaveBeenCalledWith(
      '/api/voice/synthesize',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'Hello world' }),
      }),
    )
  })

  it('speak plays audio', async () => {
    const { result } = renderHook(() => useTTS())

    act(() => result.current.setTtsEnabled(true))

    await act(async () => {
      await result.current.speak('Hello world')
    })

    expect(HTMLAudioElement.prototype.play).toHaveBeenCalled()
  })

  it('stop pauses audio', async () => {
    const { result } = renderHook(() => useTTS())

    act(() => result.current.setTtsEnabled(true))

    await act(async () => {
      await result.current.speak('Hello world')
    })

    act(() => result.current.stop())

    expect(HTMLAudioElement.prototype.pause).toHaveBeenCalled()
  })

  it('setVolume persists to localStorage', () => {
    const { result } = renderHook(() => useTTS())

    act(() => result.current.setVolume(0.5))

    expect(localStorage.getItem('ganesh_tts_volume')).toBe('0.5')
    expect(result.current.volume).toBe(0.5)
  })

  it('testChime calls /api/voice/chime with current volume', async () => {
    const { result } = renderHook(() => useTTS())

    act(() => result.current.setVolume(0.7))

    await act(async () => {
      await result.current.testChime()
    })

    expect(mockSidecarFetch).toHaveBeenCalledWith(
      '/api/voice/chime',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ volume: 0.7 }),
      }),
    )
  })

  it('ttsEnabled = false prevents speak', async () => {
    const { result } = renderHook(() => useTTS())

    await act(async () => {
      await result.current.speak('Hello world')
    })

    expect(mockSidecarFetch).not.toHaveBeenCalledWith(
      '/api/voice/synthesize',
      expect.anything(),
    )
    expect(mockSidecarFetch).not.toHaveBeenCalledWith(
      '/api/voice/synthesize-stream',
      expect.anything(),
    )
  })

  it('speakStreaming chunks text at sentence breakpoints', async () => {
    const { result } = renderHook(() => useTTS())
    act(() => result.current.setTtsEnabled(true))

    await act(async () => {
      await result.current.speakStreaming('Hello world. This is a test.', false)
    })

    expect(mockSidecarFetch).toHaveBeenCalledWith(
      '/api/voice/synthesize',
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('Hello world.'),
      }),
    )
  })

  it('speakStreaming does not synthesize when no breakpoint found', async () => {
    const { result } = renderHook(() => useTTS())
    act(() => result.current.setTtsEnabled(true))

    mockSidecarFetch.mockClear()

    await act(async () => {
      await result.current.speakStreaming('no breakpoint here', false)
    })

    expect(mockSidecarFetch).not.toHaveBeenCalled()
  })

  it('speakStreaming with isFinal synthesizes remaining text', async () => {
    const { result } = renderHook(() => useTTS())
    act(() => result.current.setTtsEnabled(true))

    await act(async () => {
      await result.current.speakStreaming('First sentence. ', false)
    })

    mockSidecarFetch.mockClear()

    await act(async () => {
      await result.current.speakStreaming('First sentence. Remaining text', true)
    })

    expect(mockSidecarFetch).toHaveBeenCalledWith(
      '/api/voice/synthesize',
      expect.objectContaining({
        body: expect.stringContaining('Remaining text'),
      }),
    )
  })

  it('speakStreaming strips markdown before synthesis', async () => {
    const { result } = renderHook(() => useTTS())
    act(() => result.current.setTtsEnabled(true))

    mockSidecarFetch.mockClear()

    await act(async () => {
      await result.current.speakStreaming('**bold text** here. ', false)
    })

    expect(mockSidecarFetch).toHaveBeenCalledWith(
      '/api/voice/synthesize',
      expect.objectContaining({
        body: JSON.stringify({ text: 'bold text here.' }),
      }),
    )
  })

  it('speakStreaming chunks at paragraph boundaries', async () => {
    const { result } = renderHook(() => useTTS())
    act(() => result.current.setTtsEnabled(true))

    mockSidecarFetch.mockClear()

    await act(async () => {
      await result.current.speakStreaming('Para one\n\nPara two', false)
    })

    expect(mockSidecarFetch).toHaveBeenCalledTimes(1)
    expect(mockSidecarFetch).toHaveBeenCalledWith(
      '/api/voice/synthesize',
      expect.objectContaining({
        body: expect.stringContaining('Para one'),
      }),
    )
  })

  it('speakStreaming chunks at list item boundaries', async () => {
    const { result } = renderHook(() => useTTS())
    act(() => result.current.setTtsEnabled(true))

    mockSidecarFetch.mockClear()

    await act(async () => {
      await result.current.speakStreaming('Intro text\n- item one', false)
    })

    expect(mockSidecarFetch).toHaveBeenCalledTimes(1)
  })

  it('resetStream clears stream state', async () => {
    const { result } = renderHook(() => useTTS())
    act(() => result.current.setTtsEnabled(true))

    await act(async () => {
      await result.current.speakStreaming('First sentence. ', false)
    })

    act(() => result.current.resetStream())

    mockSidecarFetch.mockClear()

    await act(async () => {
      await result.current.speakStreaming('First sentence. ', false)
    })

    expect(mockSidecarFetch).toHaveBeenCalled()
  })

  it('flushStream synthesizes remaining unsynthesized text', async () => {
    const { result } = renderHook(() => useTTS())
    act(() => result.current.setTtsEnabled(true))

    await act(async () => {
      await result.current.speakStreaming('no breakpoint', false)
    })

    mockSidecarFetch.mockClear()

    await act(async () => {
      await result.current.flushStream()
    })

    expect(mockSidecarFetch).toHaveBeenCalledWith(
      '/api/voice/synthesize',
      expect.objectContaining({
        body: expect.stringContaining('no breakpoint'),
      }),
    )
  })

  it('stop clears the playback queue and resets stream', async () => {
    const { result } = renderHook(() => useTTS())
    act(() => result.current.setTtsEnabled(true))

    await act(async () => {
      await result.current.speakStreaming('First sentence. ', false)
    })

    act(() => result.current.stop())

    expect(result.current.isSpeaking).toBe(false)
  })

  it('ttsEnabled = false prevents speakStreaming', async () => {
    const { result } = renderHook(() => useTTS())

    mockSidecarFetch.mockClear()

    await act(async () => {
      await result.current.speakStreaming('Hello world. Test. ', false)
    })

    expect(mockSidecarFetch).not.toHaveBeenCalled()
  })
})
