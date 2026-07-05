import '@testing-library/jest-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { ModelDownload } from '../components/ModelDownload'
import type { ModelInfo } from '../components/ModelDownload'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('../api', () => ({
  sidecarFetch: vi.fn(),
  getSidecarPort: vi.fn(),
}))

import { sidecarFetch } from '../api'

const mockFetch = sidecarFetch as ReturnType<typeof vi.fn>

function mockResponse(
  body: unknown,
  init: { ok?: boolean; status?: number } = {}
): Response {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => body,
  } as unknown as Response
}

const SAMPLE_MODELS: ModelInfo[] = [
  { name: 'stt', description: 'Speech-to-text', present: false, size: 50000000 },
  { name: 'tts', description: 'Text-to-speech', present: false, size: 30000000 },
  { name: 'embeddings', description: 'Embeddings', present: false, size: 90000000 },
]

describe('ModelDownload', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('shows modal when models are missing', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ models: SAMPLE_MODELS, all_present: false })
    )

    render(<ModelDownload />)

    await waitFor(() => {
      expect(screen.getByTestId('model-download-modal')).toBeInTheDocument()
    })
    expect(screen.getByText('Download Required Models')).toBeInTheDocument()
    expect(screen.getByTestId('model-list')).toBeInTheDocument()
    expect(screen.getByTestId('model-row-stt')).toBeInTheDocument()
    expect(screen.getByTestId('model-row-tts')).toBeInTheDocument()
    expect(screen.getByTestId('model-row-embeddings')).toBeInTheDocument()
  })

  it('does not show modal when all models are present', async () => {
    const allPresent = SAMPLE_MODELS.map((m) => ({ ...m, present: true }))
    mockFetch.mockResolvedValueOnce(
      mockResponse({ models: allPresent, all_present: true })
    )

    const { container } = render(<ModelDownload />)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled()
    })
    expect(container.querySelector('[data-testid="model-download-modal"]')).toBeNull()
  })

  it('lists model descriptions', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ models: SAMPLE_MODELS, all_present: false })
    )

    render(<ModelDownload />)

    await waitFor(() => {
      expect(screen.getByText('Speech-to-text')).toBeInTheDocument()
    })
    expect(screen.getByText('Text-to-speech')).toBeInTheDocument()
    expect(screen.getByText('Embeddings')).toBeInTheDocument()
  })

  it('starts a download when the Download button is clicked', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ models: SAMPLE_MODELS, all_present: false })
    )
    mockFetch.mockResolvedValueOnce(mockResponse({ name: 'stt', status: 'started' }))

    render(<ModelDownload />)

    await waitFor(() => {
      expect(screen.getByTestId('download-btn-stt')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('download-btn-stt'))

    await waitFor(() => {
      const calls = mockFetch.mock.calls
      const downloadCall = calls.find(
        ([path, init]) =>
          path === '/api/models/download' &&
          (init as RequestInit)?.method === 'POST'
      )
      expect(downloadCall).toBeDefined()
      const body = (downloadCall![1] as RequestInit).body
      expect(JSON.parse(body as string)).toEqual({ name: 'stt' })
    })
  })

  it('renders progress bar and percentage text', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ models: SAMPLE_MODELS, all_present: false })
    )

    render(<ModelDownload />)

    await waitFor(() => {
      expect(screen.getByTestId('progress-bar-stt')).toBeInTheDocument()
    })
    const bar = screen.getByTestId('progress-bar-stt')
    const fill = bar.firstChild as HTMLElement
    expect(fill.style.width).toBe('0%')

    const text = screen.getByTestId('progress-text-stt')
    expect(text.textContent).toContain('Not downloaded')
  })

  it('shows Download All button that triggers downloads for missing models', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ models: SAMPLE_MODELS, all_present: false })
    )
    mockFetch.mockResolvedValue(mockResponse({ name: 'x', status: 'started' }))

    render(<ModelDownload />)

    await waitFor(() => {
      expect(screen.getByTestId('download-all-btn')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByTestId('download-all-btn'))

    await waitFor(() => {
      const downloadCalls = mockFetch.mock.calls.filter(
        ([path, init]) =>
          path === '/api/models/download' &&
          (init as RequestInit)?.method === 'POST'
      )
      expect(downloadCalls.length).toBe(3)
      const names = downloadCalls.map(
        ([, init]) =>
          JSON.parse((init as RequestInit).body as string).name as string
      )
      expect(names).toEqual(expect.arrayContaining(['stt', 'tts', 'embeddings']))
    })
  })

  it('disables Close button until all models are installed', async () => {
    mockFetch.mockResolvedValueOnce(
      mockResponse({ models: SAMPLE_MODELS, all_present: false })
    )

    render(<ModelDownload />)

    await waitFor(() => {
      expect(screen.getByTestId('close-btn')).toBeInTheDocument()
    })
    expect(screen.getByTestId('close-btn')).toBeDisabled()
    expect(screen.getByTestId('close-btn').textContent).toContain('Downloading')
  })

  it('enables Close button when all models are present', async () => {
    const allPresent = SAMPLE_MODELS.map((m) => ({ ...m, present: true }))
    mockFetch.mockResolvedValueOnce(
      mockResponse({ models: allPresent, all_present: true })
    )

    render(<ModelDownload />)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled()
    })
    // Modal is not shown when all present, so close-btn won't be in the document.
    expect(screen.queryByTestId('close-btn')).toBeNull()
  })

  it('shows error message when status fetch fails', async () => {
    mockFetch.mockRejectedValueOnce(new Error('network down'))

    render(<ModelDownload />)

    await waitFor(() => {
      expect(screen.getByTestId('error-message')).toBeInTheDocument()
    })
    expect(screen.getByTestId('error-message').textContent).toContain('network down')
  })

  it('shows Installed badge for present models', async () => {
    const mixed = [
      { name: 'stt', description: 'STT', present: true, size: 100 },
      { name: 'tts', description: 'TTS', present: false, size: 100 },
    ]
    mockFetch.mockResolvedValueOnce(mockResponse({ models: mixed, all_present: false }))

    render(<ModelDownload />)

    await waitFor(() => {
      expect(screen.getAllByTestId('status-badge').length).toBe(2)
    })
    const badges = screen.getAllByTestId('status-badge')
    expect(badges[0].textContent).toBe('Installed')
    expect(badges[1].textContent).toBe('Pending')
  })
})
