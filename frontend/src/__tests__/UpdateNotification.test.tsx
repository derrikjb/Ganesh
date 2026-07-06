import '@testing-library/jest-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { UpdateNotification } from '../components/UpdateNotification'
import type { UpdateInfo, DownloadProgress } from '../api/update'

const mockInvoke = vi.fn()
const mockListen = vi.fn()

vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}))

vi.mock('@tauri-apps/api/event', () => ({
  listen: (...args: unknown[]) => mockListen(...args),
}))

vi.mock('../api', () => ({
  sidecarFetch: vi.fn(),
  getSidecarPort: vi.fn(),
}))

function makeUpdateInfo(overrides: Partial<UpdateInfo> = {}): UpdateInfo {
  return {
    available: true,
    version: '0.2.0',
    current_version: '0.1.0',
    body: 'Bug fixes and improvements',
    date: '2026-07-05',
    download_url: 'https://example.com/update',
    ...overrides,
  }
}

function setupEventListeners() {
  const handlers: Record<string, (payload: unknown) => void> = {}
  mockListen.mockImplementation(async (eventName: string, cb: (event: { payload: unknown }) => void) => {
    handlers[eventName] = (payload: unknown) => cb({ payload })
    return () => {}
  })
  return {
    emit: (eventName: string, payload: unknown) => {
      handlers[eventName]?.(payload)
    },
  }
}

describe('UpdateNotification', () => {
  beforeEach(() => {
    mockInvoke.mockReset()
    mockListen.mockReset()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  describe('test_update_check', () => {
    it('shows nothing when no update is available', async () => {
      mockInvoke.mockResolvedValueOnce(makeUpdateInfo({ available: false, version: null }))
      setupEventListeners()

      const { container } = render(<UpdateNotification autoCheckOnMount />)

      await waitFor(() => {
        expect(mockInvoke).toHaveBeenCalledWith('check_update')
      })

      expect(container.querySelector('[data-testid="update-notification"]')).toBeNull()
    })

    it('shows update banner when an update is available via auto-check', async () => {
      mockInvoke.mockResolvedValueOnce(makeUpdateInfo())
      setupEventListeners()

      render(<UpdateNotification autoCheckOnMount />)

      await waitFor(() => {
        expect(screen.getByTestId('update-notification')).toBeInTheDocument()
      })
      expect(screen.getByText(/Update available — v0\.2\.0/)).toBeInTheDocument()
      expect(screen.getByTestId('update-download-btn')).toBeInTheDocument()
    })

    it('shows update banner when update://available event fires', async () => {
      setupEventListeners()
      const { emit } = setupEventListeners()

      render(<UpdateNotification />)

      emit('update://available', '0.3.0')

      await waitFor(() => {
        expect(screen.getByTestId('update-notification')).toBeInTheDocument()
      })
      expect(screen.getByText(/Update available — v0\.3\.0/)).toBeInTheDocument()
    })

    it('shows checking status during manual check', async () => {
      let resolveCheck: (value: UpdateInfo) => void
      mockInvoke.mockReturnValueOnce(
        new Promise<UpdateInfo>((resolve) => {
          resolveCheck = resolve
        }),
      )
      setupEventListeners()

      render(<UpdateNotification autoCheckOnMount />)

      await waitFor(() => {
        expect(screen.getByTestId('update-checking')).toBeInTheDocument()
      })

      resolveCheck!(makeUpdateInfo({ available: false, version: null }))

      await waitFor(() => {
        expect(screen.queryByTestId('update-checking')).toBeNull()
      })
    })

    it('shows error when check fails', async () => {
      mockInvoke.mockRejectedValueOnce(new Error('Network error'))
      setupEventListeners()

      render(<UpdateNotification autoCheckOnMount />)

      await waitFor(() => {
        expect(screen.getByTestId('update-error')).toBeInTheDocument()
      })
      expect(screen.getByText('Network error')).toBeInTheDocument()
    })

    it('can be dismissed', async () => {
      mockInvoke.mockResolvedValueOnce(makeUpdateInfo())
      setupEventListeners()

      render(<UpdateNotification autoCheckOnMount />)

      await waitFor(() => {
        expect(screen.getByTestId('update-notification')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByTestId('update-dismiss'))

      expect(screen.queryByTestId('update-notification')).toBeNull()
    })
  })

  describe('test_update_download_progress', () => {
    it('shows progress bar during download', async () => {
      mockInvoke.mockResolvedValueOnce(makeUpdateInfo())
      const { emit } = setupEventListeners()

      render(<UpdateNotification autoCheckOnMount />)

      await waitFor(() => {
        expect(screen.getByTestId('update-download-btn')).toBeInTheDocument()
      })

      let resolveDownload: (value: boolean) => void
      mockInvoke.mockReturnValueOnce(
        new Promise<boolean>((resolve) => {
          resolveDownload = resolve
        }),
      )

      fireEvent.click(screen.getByTestId('update-download-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('update-downloading')).toBeInTheDocument()
      })
      expect(screen.getByTestId('update-progress-bar')).toBeInTheDocument()
      expect(screen.getByTestId('update-cancel-btn')).toBeInTheDocument()

      emit('update://progress', { downloaded: 500, total: 1000 } as DownloadProgress)

      await waitFor(() => {
        expect(screen.getByTestId('update-progress-text').textContent).toBe('50%')
      })

      resolveDownload!(true)

      await waitFor(() => {
        expect(screen.getByTestId('update-ready')).toBeInTheDocument()
      })
    })

    it('transitions to ready when download completes', async () => {
      mockInvoke.mockResolvedValueOnce(makeUpdateInfo())
      const { emit } = setupEventListeners()

      render(<UpdateNotification autoCheckOnMount />)

      await waitFor(() => {
        expect(screen.getByTestId('update-download-btn')).toBeInTheDocument()
      })

      mockInvoke.mockResolvedValueOnce(true)
      fireEvent.click(screen.getByTestId('update-download-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('update-downloading')).toBeInTheDocument()
      })

      emit('update://download-complete', 50000000)

      await waitFor(() => {
        expect(screen.getByTestId('update-ready')).toBeInTheDocument()
      })
      expect(screen.getByTestId('update-install-btn')).toBeInTheDocument()
    })

    it('shows installing status when install is triggered', async () => {
      mockInvoke.mockResolvedValueOnce(makeUpdateInfo())
      const { emit } = setupEventListeners()

      render(<UpdateNotification autoCheckOnMount />)

      await waitFor(() => {
        expect(screen.getByTestId('update-download-btn')).toBeInTheDocument()
      })

      mockInvoke.mockResolvedValueOnce(true)
      fireEvent.click(screen.getByTestId('update-download-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('update-downloading')).toBeInTheDocument()
      })

      emit('update://download-complete', 50000000)

      await waitFor(() => {
        expect(screen.getByTestId('update-install-btn')).toBeInTheDocument()
      })

      mockInvoke.mockResolvedValueOnce(true)
      fireEvent.click(screen.getByTestId('update-install-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('update-installing')).toBeInTheDocument()
      })
    })
  })

  describe('test_update_cancel', () => {
    it('cancels download and returns to available state', async () => {
      mockInvoke.mockResolvedValueOnce(makeUpdateInfo())
      setupEventListeners()

      render(<UpdateNotification autoCheckOnMount />)

      await waitFor(() => {
        expect(screen.getByTestId('update-download-btn')).toBeInTheDocument()
      })

      let resolveDownload: (value: boolean) => void
      mockInvoke.mockReturnValueOnce(
        new Promise<boolean>((resolve) => {
          resolveDownload = resolve
        }),
      )

      fireEvent.click(screen.getByTestId('update-download-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('update-downloading')).toBeInTheDocument()
      })

      mockInvoke.mockResolvedValueOnce(true)
      fireEvent.click(screen.getByTestId('update-cancel-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('update-download-btn')).toBeInTheDocument()
      })
      expect(screen.queryByTestId('update-downloading')).toBeNull()

      resolveDownload!(false)
    })

    it('cancel returns false from download_update and shows available again', async () => {
      mockInvoke.mockResolvedValueOnce(makeUpdateInfo())
      setupEventListeners()

      render(<UpdateNotification autoCheckOnMount />)

      await waitFor(() => {
        expect(screen.getByTestId('update-download-btn')).toBeInTheDocument()
      })

      mockInvoke.mockResolvedValueOnce(false)
      fireEvent.click(screen.getByTestId('update-download-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('update-download-btn')).toBeInTheDocument()
      })
    })
  })
})
