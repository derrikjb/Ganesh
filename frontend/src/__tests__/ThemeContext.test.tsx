import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ThemeProvider, useTheme } from '../contexts/ThemeContext'

function TestConsumer() {
  const { theme } = useTheme()
  return <div data-testid="theme-value">{theme}</div>
}

describe('ThemeContext', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
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
})
