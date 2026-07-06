import '@testing-library/jest-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import {
  AccessibilityProvider,
  useAccessibility,
} from '../contexts/AccessibilityContext'
import { VisualizerStateProvider } from '../contexts/VisualizerStateContext'
import { AccessibilitySettings } from '../components/AccessibilitySettings'
import { ChatContainer } from '../components/ChatContainer'
import { ChatInput } from '../components/ChatInput'

vi.mock('@tauri-apps/api/core', () => ({ invoke: vi.fn() }))
vi.mock('../api', () => ({
  sidecarFetch: vi.fn(),
  getSidecarPort: vi.fn(),
}))

const STORAGE_KEY = 'ganesh.a11y'

function StateProbe() {
  const s = useAccessibility()
  return (
    <div>
      <span data-testid="text-only">{String(s.textOnlyMode)}</span>
      <span data-testid="font-size">{s.fontSize}</span>
      <span data-testid="high-contrast">{String(s.highContrast)}</span>
      <span data-testid="reduced-motion">{String(s.reducedMotion)}</span>
    </div>
  )
}

function renderWithProvider(ui: React.ReactNode) {
  return render(
    <AccessibilityProvider>
      <VisualizerStateProvider>{ui}</VisualizerStateProvider>
    </AccessibilityProvider>
  )
}

describe('AccessibilityContext', () => {
  beforeEach(() => {
    window.localStorage.clear()
    document.documentElement.removeAttribute('data-text-only')
    document.documentElement.removeAttribute('data-font-size')
    document.documentElement.removeAttribute('data-contrast')
    document.documentElement.removeAttribute('data-motion')
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('exposes default state', () => {
    renderWithProvider(<StateProbe />)
    expect(screen.getByTestId('text-only').textContent).toBe('false')
    expect(screen.getByTestId('font-size').textContent).toBe('medium')
    expect(screen.getByTestId('high-contrast').textContent).toBe('false')
    expect(screen.getByTestId('reduced-motion').textContent).toBe('false')
  })

  it('throws when used outside provider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<StateProbe />)).toThrow(
      'useAccessibility must be used within an AccessibilityProvider',
    )
    spy.mockRestore()
  })

  it('reflects state onto documentElement data attributes', () => {
    renderWithProvider(<StateProbe />)
    expect(document.documentElement.getAttribute('data-text-only')).toBe('off')
    expect(document.documentElement.getAttribute('data-font-size')).toBe('medium')
    expect(document.documentElement.getAttribute('data-contrast')).toBe('normal')
    expect(document.documentElement.getAttribute('data-motion')).toBe('normal')
  })
})

describe('AccessibilitySettings', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('toggles text-only mode', () => {
    renderWithProvider(<AccessibilitySettings />)
    const toggle = screen.getByTestId('toggle-text-only-mode')
    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-checked', 'true')
  })

  it('changes font size', () => {
    renderWithProvider(<AccessibilitySettings />)
    const large = screen.getByTestId('font-size-large')
    fireEvent.click(large)
    expect(large).toHaveAttribute('aria-pressed', 'true')
    expect(document.documentElement.getAttribute('data-font-size')).toBe('large')
  })

  it('applies high contrast styles', () => {
    renderWithProvider(<AccessibilitySettings />)
    const toggle = screen.getByTestId('toggle-high-contrast')
    fireEvent.click(toggle)
    expect(document.documentElement.getAttribute('data-contrast')).toBe('high')
  })

  it('applies reduced motion', () => {
    renderWithProvider(<AccessibilitySettings />)
    const toggle = screen.getByTestId('toggle-reduced-motion')
    fireEvent.click(toggle)
    expect(document.documentElement.getAttribute('data-motion')).toBe('reduced')
  })

  it('persists settings to localStorage', async () => {
    renderWithProvider(<AccessibilitySettings />)
    fireEvent.click(screen.getByTestId('toggle-text-only-mode'))
    fireEvent.click(screen.getByTestId('font-size-large'))
    fireEvent.click(screen.getByTestId('toggle-high-contrast'))
    fireEvent.click(screen.getByTestId('toggle-reduced-motion'))

    await waitFor(() => {
      const raw = window.localStorage.getItem(STORAGE_KEY)
      expect(raw).not.toBeNull()
      const parsed = JSON.parse(raw!)
      expect(parsed.textOnlyMode).toBe(true)
      expect(parsed.fontSize).toBe('large')
      expect(parsed.highContrast).toBe(true)
      expect(parsed.reducedMotion).toBe(true)
    })
  })

  it('restores settings from localStorage on mount', () => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        textOnlyMode: true,
        fontSize: 'large',
        highContrast: true,
        reducedMotion: true,
      }),
    )
    renderWithProvider(<StateProbe />)
    expect(screen.getByTestId('text-only').textContent).toBe('true')
    expect(screen.getByTestId('font-size').textContent).toBe('large')
    expect(screen.getByTestId('high-contrast').textContent).toBe('true')
    expect(screen.getByTestId('reduced-motion').textContent).toBe('true')
  })

  it('resets to defaults', () => {
    renderWithProvider(<AccessibilitySettings />)
    fireEvent.click(screen.getByTestId('toggle-text-only-mode'))
    fireEvent.click(screen.getByTestId('reset-a11y'))
    expect(screen.getByTestId('toggle-text-only-mode')).toHaveAttribute(
      'aria-checked',
      'false',
    )
  })
})

describe('text-only mode hides voice UI', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('hides voice controls and mic button when text-only mode is enabled', () => {
    function Harness() {
      const { setTextOnlyMode } = useAccessibility()
      return (
        <>
          <button onClick={() => setTextOnlyMode(true)} data-testid="enable">
            enable
          </button>
          <ChatContainer documents={[]} onOpenDocument={() => {}} />
        </>
      )
    }

    renderWithProvider(<Harness />)

    expect(screen.getByTestId('voice-controls')).toBeInTheDocument()
    expect(screen.getByTestId('mic-button')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('enable'))

    expect(screen.queryByTestId('voice-controls')).not.toBeInTheDocument()
    expect(screen.queryByTestId('mic-button')).not.toBeInTheDocument()
    expect(screen.getByTestId('text-only-banner')).toBeInTheDocument()
  })

  it('shows send confirmation feedback on send', async () => {
    renderWithProvider(<ChatInput onSend={vi.fn()} disabled={false} />)
    fireEvent.change(screen.getByTestId('chat-textarea'), {
      target: { value: 'hello' },
    })
    fireEvent.click(screen.getByTestId('send-button'))

    expect(screen.getByTestId('send-confirmation')).toBeInTheDocument()
    await waitFor(
      () => {
        expect(screen.queryByTestId('send-confirmation')).not.toBeInTheDocument()
      },
      { timeout: 2000 },
    )
  })
})
