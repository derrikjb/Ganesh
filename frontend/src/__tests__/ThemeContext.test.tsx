import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { ThemeProvider, useTheme } from '../contexts/ThemeContext'

function TestConsumer() {
  const { theme, customizations, setTheme, setCustomizations, resetCustomizations } = useTheme()
  return (
    <div>
      <div data-testid="theme-value">{theme}</div>
      <div data-testid="customizations">{JSON.stringify(customizations)}</div>
      <button onClick={() => setTheme('midnight')} data-testid="set-midnight">Set Midnight</button>
      <button onClick={() => setTheme('ocean')} data-testid="set-ocean">Set Ocean</button>
      <button onClick={() => setTheme('forest')} data-testid="set-forest">Set Forest</button>
      <button onClick={() => setTheme('custom')} data-testid="set-custom">Set Custom</button>
      <button onClick={() => setCustomizations({ accentColor: '#ff0000' })} data-testid="set-accent">Set Accent</button>
      <button onClick={resetCustomizations} data-testid="reset-custom">Reset</button>
    </div>
  )
}

describe('ThemeContext', () => {
  beforeEach(() => {
    cleanup()
    vi.restoreAllMocks()
    localStorage.clear()
  })

  afterEach(() => {
    cleanup()
    localStorage.clear()
  })

  it('provides dark theme as default', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>,
    )

    expect(screen.getByTestId('theme-value').textContent).toBe('dark')
  })

  it('sets data-theme attribute on documentElement', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>,
    )

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('sets colorScheme style on documentElement', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>,
    )

    expect(document.documentElement.style.colorScheme).toBe('dark')
  })

  it('throws when useTheme is used outside ThemeProvider', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    expect(() => render(<TestConsumer />)).toThrow(
      'useTheme must be used within a ThemeProvider',
    )

    consoleError.mockRestore()
  })

  it('changes theme when setTheme is called', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>,
    )

    fireEvent.click(screen.getByTestId('set-midnight'))
    expect(screen.getByTestId('theme-value').textContent).toBe('midnight')
    expect(document.documentElement.getAttribute('data-theme')).toBe('midnight')

    fireEvent.click(screen.getByTestId('set-ocean'))
    expect(screen.getByTestId('theme-value').textContent).toBe('ocean')
    expect(document.documentElement.getAttribute('data-theme')).toBe('ocean')

    fireEvent.click(screen.getByTestId('set-forest'))
    expect(screen.getByTestId('theme-value').textContent).toBe('forest')
    expect(document.documentElement.getAttribute('data-theme')).toBe('forest')
  })

  it('applies customizations when setCustomizations is called', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>,
    )

    fireEvent.click(screen.getByTestId('set-accent'))
    expect(screen.getByTestId('customizations').textContent).toContain('#ff0000')
  })

  it('resets customizations when resetCustomizations is called', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>,
    )

    fireEvent.click(screen.getByTestId('set-accent'))
    expect(screen.getByTestId('customizations').textContent).toContain('#ff0000')

    fireEvent.click(screen.getByTestId('reset-custom'))
    expect(screen.getByTestId('customizations').textContent).toBe('{}')
  })

  it('persists theme to localStorage', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>,
    )

    fireEvent.click(screen.getByTestId('set-midnight'))
    expect(localStorage.getItem('ganesh-theme')).toBe('midnight')
  })

  it('persists customizations to localStorage', () => {
    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>,
    )

    fireEvent.click(screen.getByTestId('set-accent'))
    expect(localStorage.getItem('ganesh-theme-customizations')).toContain('#ff0000')
  })

  it('loads saved theme from localStorage on init', () => {
    localStorage.setItem('ganesh-theme', 'ocean')
    localStorage.setItem('ganesh-theme-customizations', JSON.stringify({ accentColor: '#00ff00' }))

    render(
      <ThemeProvider>
        <TestConsumer />
      </ThemeProvider>,
    )

    expect(screen.getByTestId('theme-value').textContent).toBe('ocean')
    expect(screen.getByTestId('customizations').textContent).toContain('#00ff00')
  })
})
