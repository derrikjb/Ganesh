import '@testing-library/jest-dom'
import '@testing-library/jest-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { ThemeProvider, useTheme } from '../contexts/ThemeContext'
import { ThemeSwitcher } from '../components/ThemeSwitcher'

function ThemeTestConsumer() {
  const { theme, customizations } = useTheme()
  return (
    <div>
      <div data-testid="theme-value">{theme}</div>
      <div data-testid="customizations-value">{JSON.stringify(customizations)}</div>
    </div>
  )
}

function ThemeSwitcherWrapper() {
  return (
    <ThemeProvider>
      <ThemeSwitcher />
      <ThemeTestConsumer />
    </ThemeProvider>
  )
}

describe('ThemeSwitcher', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    cleanup()
  })

  afterEach(() => {
    localStorage.clear()
    cleanup()
  })

  afterEach(() => {
    localStorage.clear()
    cleanup()
  })

  it('renders theme switcher with all preset previews', () => {
    render(<ThemeSwitcherWrapper />)

    expect(screen.getByTestId('theme-switcher')).toBeInTheDocument()
    expect(screen.getByTestId('theme-preview-dark')).toBeInTheDocument()
    expect(screen.getByTestId('theme-preview-midnight')).toBeInTheDocument()
    expect(screen.getByTestId('theme-preview-ocean')).toBeInTheDocument()
    expect(screen.getByTestId('theme-preview-forest')).toBeInTheDocument()
  })

  it('selecting a preset changes the theme', () => {
    render(<ThemeSwitcherWrapper />)

    fireEvent.click(screen.getByTestId('theme-preview-midnight'))
    expect(screen.getByTestId('theme-value').textContent).toBe('midnight')

    fireEvent.click(screen.getByTestId('theme-preview-ocean'))
    expect(screen.getByTestId('theme-value').textContent).toBe('ocean')

    fireEvent.click(screen.getByTestId('theme-preview-forest'))
    expect(screen.getByTestId('theme-value').textContent).toBe('forest')
  })

  it('toggles custom options panel', () => {
    render(<ThemeSwitcherWrapper />)

    expect(screen.queryByTestId('color-picker-accent')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId('toggle-custom'))
    expect(screen.getByTestId('color-picker-accent')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('toggle-custom'))
    expect(screen.queryByTestId('color-picker-accent')).not.toBeInTheDocument()
  })

  it('changing a color picker switches to custom theme', () => {
    render(<ThemeSwitcherWrapper />)

    fireEvent.click(screen.getByTestId('toggle-custom'))

    const accentPicker = screen.getByTestId('color-picker-accent')
    fireEvent.change(accentPicker, { target: { value: '#ff0000' } })

    expect(screen.getByTestId('theme-value').textContent).toBe('custom')
  })

  it('border style toggle works', () => {
    render(<ThemeSwitcherWrapper />)

    fireEvent.click(screen.getByTestId('toggle-custom'))

    fireEvent.click(screen.getByTestId('border-style-square'))
    expect(screen.getByTestId('customizations-value').textContent).toContain('square')

    fireEvent.click(screen.getByTestId('border-style-rounded'))
    expect(screen.getByTestId('customizations-value').textContent).not.toContain('square')
  })

  it('selecting preset after custom resets to preset', () => {
    render(<ThemeSwitcherWrapper />)

    fireEvent.click(screen.getByTestId('toggle-custom'))
    const accentPicker = screen.getByTestId('color-picker-accent')
    fireEvent.change(accentPicker, { target: { value: '#ff0000' } })
    expect(screen.getByTestId('theme-value').textContent).toBe('custom')

    fireEvent.click(screen.getByTestId('theme-preview-midnight'))
    expect(screen.getByTestId('theme-value').textContent).toBe('midnight')
    expect(screen.getByTestId('customizations-value').textContent).toBe('{}')
  })
})
