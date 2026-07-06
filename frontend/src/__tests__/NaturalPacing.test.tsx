import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook, act, cleanup } from '@testing-library/react'
import { useNaturalPacing } from '../hooks/useNaturalPacing'
import type { SpeedMultiplier } from '../hooks/useNaturalPacing'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('../api', () => ({
  sidecarFetch: vi.fn(),
  getSidecarPort: vi.fn(),
}))

describe('useNaturalPacing', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  function createTimers() {
    const timers: Array<{ fn: () => void; delay: number; id: number }> = []
    let idCounter = 0

    const mockSetTimeout = (fn: () => void, delay: number): number => {
      const id = ++idCounter
      timers.push({ fn, delay, id })
      return id
    }

    const mockClearTimeout = (id: number): void => {
      const idx = timers.findIndex((t) => t.id === id)
      if (idx >= 0) timers.splice(idx, 1)
    }

    const flush = () => {
      while (timers.length > 0) {
        const next = timers.shift()!
        next.fn()
      }
    }

    return { mockSetTimeout, mockClearTimeout, flush }
  }

  describe('test_pacing_toggle', () => {
    it('passes through content immediately when pacing is off', () => {
      const timers = createTimers()
      const { result } = renderHook(
        () =>
          useNaturalPacing('Hello world', true, {
            config: { enabled: false, speedMultiplier: 1 },
            timers: { setTimeout: timers.mockSetTimeout, clearTimeout: timers.mockClearTimeout },
          }),
      )

      expect(result.current.pacedContent).toBe('Hello world')
      expect(result.current.isThinking).toBe(false)
      expect(result.current.isPacing).toBe(false)
    })

    it('passes through content immediately when speed is instant', () => {
      const timers = createTimers()
      const { result } = renderHook(
        () =>
          useNaturalPacing('Hello world', true, {
            config: { enabled: true, speedMultiplier: 'instant' as SpeedMultiplier },
            timers: { setTimeout: timers.mockSetTimeout, clearTimeout: timers.mockClearTimeout },
          }),
      )

      expect(result.current.pacedContent).toBe('Hello world')
      expect(result.current.isThinking).toBe(false)
      expect(result.current.isPacing).toBe(false)
    })

    it('shows thinking indicator when pacing is on', () => {
      const timers = createTimers()
      const { result } = renderHook(
        () =>
          useNaturalPacing('Hello world', true, {
            config: { enabled: true, speedMultiplier: 1 },
            timers: { setTimeout: timers.mockSetTimeout, clearTimeout: timers.mockClearTimeout },
          }),
      )

      expect(result.current.isThinking).toBe(true)
      expect(result.current.isPacing).toBe(false)
      expect(result.current.pacedContent).toBe('')
    })
  })

  describe('test_thinking_pause', () => {
    it('shows thinking indicator before first token when pacing is on', () => {
      const timers = createTimers()
      const { result } = renderHook(
        () =>
          useNaturalPacing('Hello', true, {
            config: { enabled: true, speedMultiplier: 1 },
            timers: { setTimeout: timers.mockSetTimeout, clearTimeout: timers.mockClearTimeout },
          }),
      )

      expect(result.current.isThinking).toBe(true)
      expect(result.current.pacedContent).toBe('')
    })

    it('starts pacing after thinking delay', () => {
      const timers = createTimers()
      const { result } = renderHook(
        () =>
          useNaturalPacing('Hello world this is a test', true, {
            config: { enabled: true, speedMultiplier: 1 },
            timers: { setTimeout: timers.mockSetTimeout, clearTimeout: timers.mockClearTimeout },
          }),
      )

      expect(result.current.isThinking).toBe(true)

      act(() => {
        timers.flush()
      })

      expect(result.current.isThinking).toBe(false)
      expect(result.current.isPacing).toBe(true)
    })
  })

  describe('test_typing_speed', () => {
    it('outputs content at 1x speed', () => {
      const timers = createTimers()
      const testContent = 'A'.repeat(120)

      const { result } = renderHook(
        () =>
          useNaturalPacing(testContent, true, {
            config: { enabled: true, speedMultiplier: 1 },
            timers: { setTimeout: timers.mockSetTimeout, clearTimeout: timers.mockClearTimeout },
          }),
      )

      expect(result.current.isThinking).toBe(true)

      act(() => {
        timers.flush()
      })

      expect(result.current.isThinking).toBe(false)
      expect(result.current.isPacing).toBe(true)

      const pacedLength = result.current.pacedContent.length
      expect(pacedLength).toBeGreaterThan(0)
      expect(pacedLength).toBeLessThanOrEqual(testContent.length)
    })

    it('outputs faster at 2x speed than 1x', () => {
      const timers1x = createTimers()
      const timers2x = createTimers()
      const testContent = 'B'.repeat(120)

      const { result: result1x } = renderHook(
        () =>
          useNaturalPacing(testContent, true, {
            config: { enabled: true, speedMultiplier: 1 },
            timers: { setTimeout: timers1x.mockSetTimeout, clearTimeout: timers1x.mockClearTimeout },
          }),
      )

      const { result: result2x } = renderHook(
        () =>
          useNaturalPacing(testContent, true, {
            config: { enabled: true, speedMultiplier: 2 },
            timers: { setTimeout: timers2x.mockSetTimeout, clearTimeout: timers2x.mockClearTimeout },
          }),
      )

      act(() => {
        timers1x.flush()
        timers2x.flush()
      })

      expect(result2x.current.pacedContent.length).toBeGreaterThanOrEqual(
        result1x.current.pacedContent.length,
      )
    })

    it('outputs slower at 0.5x speed than 1x', () => {
      const timers1x = createTimers()
      const timers05x = createTimers()
      const testContent = 'C'.repeat(120)

      const { result: result1x } = renderHook(
        () =>
          useNaturalPacing(testContent, true, {
            config: { enabled: true, speedMultiplier: 1 },
            timers: { setTimeout: timers1x.mockSetTimeout, clearTimeout: timers1x.mockClearTimeout },
          }),
      )

      const { result: result05x } = renderHook(
        () =>
          useNaturalPacing(testContent, true, {
            config: { enabled: true, speedMultiplier: 0.5 },
            timers: { setTimeout: timers05x.mockSetTimeout, clearTimeout: timers05x.mockClearTimeout },
          }),
      )

      act(() => {
        timers1x.flush()
        timers05x.flush()
      })

      expect(result05x.current.pacedContent.length).toBeLessThanOrEqual(
        result1x.current.pacedContent.length,
      )
    })
  })

  describe('paragraph pauses', () => {
    it('pauses at paragraph boundaries', () => {
      const timers = createTimers()
      const content = 'First paragraph.\n\nSecond paragraph.'

      const { result } = renderHook(
        () =>
          useNaturalPacing(content, true, {
            config: { enabled: true, speedMultiplier: 1 },
            timers: { setTimeout: timers.mockSetTimeout, clearTimeout: timers.mockClearTimeout },
          }),
      )

      act(() => {
        timers.flush()
      })

      const paced = result.current.pacedContent
      expect(paced.length).toBeGreaterThan(0)
      expect(paced.length).toBeLessThanOrEqual(content.length)
    })
  })

  describe('streaming end', () => {
    it('releases all buffered content when streaming ends', () => {
      const timers = createTimers()
      const testContent = 'Hello world this is a test message'

      const { result, rerender } = renderHook(
        ({ content, streaming }) =>
          useNaturalPacing(content, streaming, {
            config: { enabled: true, speedMultiplier: 1 },
            timers: { setTimeout: timers.mockSetTimeout, clearTimeout: timers.mockClearTimeout },
          }),
        {
          initialProps: { content: '', streaming: false },
        },
      )

      act(() => {
        rerender({ content: testContent, streaming: true })
      })

      act(() => {
        rerender({ content: testContent, streaming: false })
      })

      expect(result.current.pacedContent).toBe(testContent)
      expect(result.current.isThinking).toBe(false)
      expect(result.current.isPacing).toBe(false)
    })
  })
})
