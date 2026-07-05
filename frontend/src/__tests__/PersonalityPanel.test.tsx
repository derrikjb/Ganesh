import '@testing-library/jest-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { PersonalityPanel } from '../components/PersonalityPanel'

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

const SAMPLE_PAYLOAD = {
  traits: {
    formality: 0.1,
    verbosity: -0.2,
    warmth: 0.7,
    humor: 0.4,
    assertiveness: 0.0,
  },
  baseline: {
    formality: 0.0,
    verbosity: 0.0,
    warmth: 0.5,
    humor: 0.3,
    assertiveness: 0.0,
  },
  locked: ['formality'],
  persisted: true,
}

describe('PersonalityPanel', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders traits with current and baseline values', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse(SAMPLE_PAYLOAD))

    render(<PersonalityPanel refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('trait-formality')).toBeInTheDocument()
    })

    expect(screen.getByTestId('trait-formality-value').textContent).toBe('0.10')
    expect(screen.getByTestId('trait-formality-baseline').textContent).toBe(
      'baseline: 0.00',
    )
    expect(screen.getByTestId('trait-warmth-value').textContent).toBe('0.70')
    expect(screen.getByTestId('trait-humor-value').textContent).toBe('0.40')
    expect(screen.getByTestId('slider-formality')).toHaveValue('0.1')
  })

  it('shows lock state and toggles lock via POST', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse(SAMPLE_PAYLOAD))
    const unlockedPayload = { ...SAMPLE_PAYLOAD, locked: [] }
    mockFetch.mockResolvedValueOnce(mockResponse(unlockedPayload))

    render(<PersonalityPanel refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('trait-formality-lock')).toBeInTheDocument()
    })

    const lockBtn = screen.getByTestId('trait-formality-lock')
    expect(lockBtn).toHaveAttribute('aria-pressed', 'true')

    fireEvent.click(lockBtn)

    await waitFor(() => {
      const unlockCall = mockFetch.mock.calls.find(
        ([path, init]) =>
          path === '/api/personality/unlock/formality?persist=true' &&
          (init as RequestInit)?.method === 'POST',
      )
      expect(unlockCall).toBeDefined()
    })
  })

  it('sends PUT /api/personality/traits when slider changes', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse(SAMPLE_PAYLOAD))
    const updatedPayload = {
      ...SAMPLE_PAYLOAD,
      traits: { ...SAMPLE_PAYLOAD.traits, warmth: 0.8 },
    }
    mockFetch.mockResolvedValueOnce(mockResponse(updatedPayload))

    render(<PersonalityPanel refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('slider-warmth')).toBeInTheDocument()
    })

    const slider = screen.getByTestId('slider-warmth') as HTMLInputElement
    fireEvent.change(slider, { target: { value: '0.8' } })

    await waitFor(() => {
      const putCall = mockFetch.mock.calls.find(
        ([path, init]) =>
          path === '/api/personality/traits?persist=true' &&
          (init as RequestInit)?.method === 'PUT',
      )
      expect(putCall).toBeDefined()
    })
  })

  it('triggers reset via POST /api/personality/reset', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse(SAMPLE_PAYLOAD))
    const resetPayload = {
      traits: SAMPLE_PAYLOAD.baseline,
      baseline: SAMPLE_PAYLOAD.baseline,
      locked: [],
      persisted: true,
    }
    mockFetch.mockResolvedValueOnce(mockResponse(resetPayload))

    render(<PersonalityPanel refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('personality-reset')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('personality-reset'))

    await waitFor(() => {
      const resetCall = mockFetch.mock.calls.find(
        ([path, init]) =>
          path === '/api/personality/reset' &&
          (init as RequestInit)?.method === 'POST',
      )
      expect(resetCall).toBeDefined()
    })
  })

  it('shows persistence status indicator', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse(SAMPLE_PAYLOAD))

    render(<PersonalityPanel refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('personality-persist-status')).toBeInTheDocument()
    })

    expect(screen.getByTestId('personality-persist-status').textContent).toBe(
      'Saved',
    )
  })

  it('shows Not saved when persisted is false', async () => {
    const unsavedPayload = { ...SAMPLE_PAYLOAD, persisted: false }
    mockFetch.mockResolvedValueOnce(mockResponse(unsavedPayload))

    render(<PersonalityPanel refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('personality-persist-status')).toBeInTheDocument()
    })

    expect(screen.getByTestId('personality-persist-status').textContent).toBe(
      'Not saved',
    )
  })

  it('triggers save via POST /api/personality/save', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse(SAMPLE_PAYLOAD))
    const savedPayload = { ...SAMPLE_PAYLOAD, persisted: true }
    mockFetch.mockResolvedValueOnce(mockResponse(savedPayload))

    render(<PersonalityPanel refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('personality-save')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('personality-save'))

    await waitFor(() => {
      const saveCall = mockFetch.mock.calls.find(
        ([path, init]) =>
          path === '/api/personality/save' &&
          (init as RequestInit)?.method === 'POST',
      )
      expect(saveCall).toBeDefined()
    })
  })

  it('triggers load via POST /api/personality/load', async () => {
    mockFetch.mockResolvedValueOnce(mockResponse(SAMPLE_PAYLOAD))
    const loadedPayload = {
      ...SAMPLE_PAYLOAD,
      traits: { ...SAMPLE_PAYLOAD.traits, formality: 0.5 },
    }
    mockFetch.mockResolvedValueOnce(mockResponse(loadedPayload))

    render(<PersonalityPanel refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('personality-load')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('personality-load'))

    await waitFor(() => {
      const loadCall = mockFetch.mock.calls.find(
        ([path, init]) =>
          path === '/api/personality/load' &&
          (init as RequestInit)?.method === 'POST',
      )
      expect(loadCall).toBeDefined()
    })
  })

  it('shows error message when fetch fails', async () => {
    mockFetch.mockRejectedValueOnce(new Error('network down'))

    render(<PersonalityPanel refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('personality-error')).toBeInTheDocument()
    })
    expect(screen.getByTestId('personality-error').textContent).toContain(
      'network down',
    )
  })
})
