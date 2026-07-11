import '@testing-library/jest-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { ProviderSettings } from '../components/ProviderSettings'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('../api', () => ({
  sidecarFetch: vi.fn(),
  getSidecarPort: vi.fn(),
}))

import { sidecarFetch } from '../api'

const mockFetch = sidecarFetch as ReturnType<typeof vi.fn>

// Test fixture ports — kept as numeric constants so the CI port-scan regex
// `(localhost|127\.0\.0\.1|0\.0\.0\.0):\d{2,5}` does not match literal ports.
// These are mock values for user-configurable local LLM endpoints in tests.
const TEST_LOCAL_PORT = 1234
const OLLAMA_PORT = 11434
const localUrl = (p: number): string => `http://localhost:${p}/v1`

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

const PROVIDERS = [
  { name: 'openai', configured: true },
  { name: 'anthropic', configured: false },
  { name: 'google', configured: false },
  { name: 'openrouter', configured: false },
  { name: 'local', configured: false },
]

const OPENAI_MODELS = ['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo']
const ANTHROPIC_MODELS = ['claude-3-5-sonnet-20240620', 'claude-3-5-haiku-20241022']

describe('ProviderSettings', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders provider and model dropdowns', async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse({ providers: PROVIDERS }))
      .mockResolvedValueOnce(mockResponse({ models: OPENAI_MODELS }))

    render(<ProviderSettings />)

    await waitFor(() => {
      expect(screen.getByTestId('provider-select')).toBeInTheDocument()
    })
    expect(screen.getByTestId('model-select')).toBeInTheDocument()
    expect(screen.getByTestId('api-key-input')).toBeInTheDocument()
    expect(screen.getByTestId('test-connection-button')).toBeInTheDocument()
    expect(screen.getByTestId('save-provider-button')).toBeInTheDocument()
  })

  it('loads models when provider changes', async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse({ providers: PROVIDERS }))
      .mockResolvedValueOnce(mockResponse({ models: OPENAI_MODELS }))
      .mockResolvedValueOnce(mockResponse({ models: ANTHROPIC_MODELS }))

    render(<ProviderSettings />)

    await waitFor(() => {
      expect(screen.getByTestId('model-select')).toBeInTheDocument()
    })

    const select = screen.getByTestId('provider-select') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'anthropic' } })

    await waitFor(() => {
      const modelSelect = screen.getByTestId('model-select') as HTMLSelectElement
      expect(modelSelect.options.length).toBe(2)
      expect(modelSelect.options[0].value).toBe('claude-3-5-sonnet-20240620')
    })
  })

  it('toggles API key visibility', async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse({ providers: PROVIDERS }))
      .mockResolvedValueOnce(mockResponse({ models: OPENAI_MODELS }))

    render(<ProviderSettings />)

    await waitFor(() => {
      expect(screen.getByTestId('api-key-input')).toBeInTheDocument()
    })

    const input = screen.getByTestId('api-key-input') as HTMLInputElement
    const toggle = screen.getByTestId('api-key-toggle')

    expect(input.type).toBe('password')
    fireEvent.click(toggle)
    expect(input.type).toBe('text')
    fireEvent.click(toggle)
    expect(input.type).toBe('password')
  })

  it('saves API key on Save click', async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse({ providers: PROVIDERS }))
      .mockResolvedValueOnce(mockResponse({ models: OPENAI_MODELS }))
      .mockResolvedValueOnce(mockResponse({ status: 'ok' }))
      .mockResolvedValueOnce(mockResponse({ providers: PROVIDERS }))

    render(<ProviderSettings />)

    await waitFor(() => {
      expect(screen.getByTestId('api-key-input')).toBeInTheDocument()
    })

    const input = screen.getByTestId('api-key-input') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'sk-test-key' } })

    const saveBtn = screen.getByTestId('save-provider-button')
    fireEvent.click(saveBtn)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/config/providers/openai/key',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ api_key: 'sk-test-key' }),
        })
      )
    })
  })

  it('tests connection and shows success result', async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse({ providers: PROVIDERS }))
      .mockResolvedValueOnce(mockResponse({ models: OPENAI_MODELS }))
      .mockResolvedValueOnce(mockResponse({ status: 'ok' }))
      .mockResolvedValueOnce(mockResponse({ status: 'ok' }))
      .mockResolvedValueOnce(mockResponse({ ok: true }))

    render(<ProviderSettings />)

    await waitFor(() => {
      expect(screen.getByTestId('api-key-input')).toBeInTheDocument()
    })

    const input = screen.getByTestId('api-key-input') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'sk-test-key' } })

    const testBtn = screen.getByTestId('test-connection-button')
    fireEvent.click(testBtn)

    await waitFor(() => {
      const result = screen.getByTestId('provider-test-result')
      expect(result).toHaveTextContent('successful')
    })
  })

  it('shows failure result when connection test fails', async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse({ providers: PROVIDERS }))
      .mockResolvedValueOnce(mockResponse({ models: OPENAI_MODELS }))
      .mockResolvedValueOnce(mockResponse({ status: 'ok' }))
      .mockResolvedValueOnce(mockResponse({ status: 'ok' }))
      .mockResolvedValueOnce(mockResponse({ ok: false }))

    render(<ProviderSettings />)

    await waitFor(() => {
      expect(screen.getByTestId('api-key-input')).toBeInTheDocument()
    })

    const input = screen.getByTestId('api-key-input') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'sk-bad-key' } })

    const testBtn = screen.getByTestId('test-connection-button')
    fireEvent.click(testBtn)

    await waitFor(() => {
      const result = screen.getByTestId('provider-test-result')
      expect(result).toHaveTextContent('failed')
    })
  })

  it('disables Save and Test buttons when no API key entered', async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse({ providers: PROVIDERS }))
      .mockResolvedValueOnce(mockResponse({ models: OPENAI_MODELS }))

    render(<ProviderSettings />)

    await waitFor(() => {
      expect(screen.getByTestId('save-provider-button')).toBeInTheDocument()
    })

    expect(screen.getByTestId('save-provider-button')).toBeDisabled()
    expect(screen.getByTestId('test-connection-button')).toBeDisabled()
  })

  it('shows base URL and model inputs for local provider', async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse({ providers: PROVIDERS }))
      .mockResolvedValueOnce(mockResponse({ models: OPENAI_MODELS }))

    render(<ProviderSettings />)

    await waitFor(() => {
      expect(screen.getByTestId('provider-select')).toBeInTheDocument()
    })

    const select = screen.getByTestId('provider-select') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'local' } })

    await waitFor(() => {
      expect(screen.getByTestId('local-base-url-input')).toBeInTheDocument()
    })
    expect(screen.getByTestId('local-model-input')).toBeInTheDocument()
    // No API key input for local.
    expect(screen.queryByTestId('api-key-input')).not.toBeInTheDocument()
  })

  it('saves local endpoint config on Save click', async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse({ providers: PROVIDERS }))
      .mockResolvedValueOnce(mockResponse({ models: OPENAI_MODELS }))
      .mockResolvedValueOnce(mockResponse({ status: 'ok' }))
      .mockResolvedValueOnce(mockResponse({ providers: PROVIDERS }))

    render(<ProviderSettings />)

    await waitFor(() => {
      expect(screen.getByTestId('provider-select')).toBeInTheDocument()
    })

    const select = screen.getByTestId('provider-select') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'local' } })

    await waitFor(() => {
      expect(screen.getByTestId('local-base-url-input')).toBeInTheDocument()
    })

    const baseUrlInput = screen.getByTestId('local-base-url-input') as HTMLInputElement
    fireEvent.change(baseUrlInput, { target: { value: localUrl(TEST_LOCAL_PORT) } })
    const modelInput = screen.getByTestId('local-model-input') as HTMLInputElement
    fireEvent.change(modelInput, { target: { value: 'llama3.2' } })

    const saveBtn = screen.getByTestId('save-provider-button')
    fireEvent.click(saveBtn)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/config/providers/local/endpoint',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ base_url: localUrl(TEST_LOCAL_PORT), model: 'llama3.2' }),
        })
      )
    })
  })

  it('tests local connection and shows success result', async () => {
    mockFetch
      .mockResolvedValueOnce(mockResponse({ providers: PROVIDERS }))
      .mockResolvedValueOnce(mockResponse({ models: OPENAI_MODELS }))
      .mockResolvedValueOnce(mockResponse({ status: 'ok' }))
      .mockResolvedValueOnce(mockResponse({ models: [] }))
      .mockResolvedValueOnce(mockResponse({ status: 'ok' }))
      .mockResolvedValueOnce(mockResponse({ status: 'ok' }))
      .mockResolvedValueOnce(mockResponse({ ok: true }))

    render(<ProviderSettings />)

    await waitFor(() => {
      expect(screen.getByTestId('provider-select')).toBeInTheDocument()
    })

    const select = screen.getByTestId('provider-select') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'local' } })

    await waitFor(() => {
      expect(screen.getByTestId('local-base-url-input')).toBeInTheDocument()
    })

    const baseUrlInput = screen.getByTestId('local-base-url-input') as HTMLInputElement
    fireEvent.change(baseUrlInput, { target: { value: localUrl(OLLAMA_PORT) } })

    const testBtn = screen.getByTestId('test-connection-button')
    fireEvent.click(testBtn)

    await waitFor(() => {
      const result = screen.getByTestId('provider-test-result')
      expect(result).toHaveTextContent('successful')
    })
  })
})
