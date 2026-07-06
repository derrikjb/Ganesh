import '@testing-library/jest-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { PatternSuggestion } from '../components/PatternSuggestion'
import type { PatternSuggestionData } from '../components/PatternSuggestion'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('../api', () => ({
  sidecarFetch: vi.fn(),
  getSidecarPort: vi.fn(),
}))

function makeSuggestion(
  overrides: Partial<PatternSuggestionData> = {},
): PatternSuggestionData {
  return {
    pattern_id: 'pat-1',
    trigger: 'checks weather',
    followup: 'starts a meeting',
    confidence: 0.75,
    note: 'User often does checks weather before starts a meeting.',
    ...overrides,
  }
}

describe('PatternSuggestion', () => {
  const onAccept = vi.fn()
  const onDecline = vi.fn()
  const onDisable = vi.fn()

  beforeEach(() => {
    onAccept.mockClear()
    onDecline.mockClear()
    onDisable.mockClear()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders the suggestion text with trigger and followup', () => {
    render(
      <PatternSuggestion
        suggestion={makeSuggestion()}
        onAccept={onAccept}
        onDecline={onDecline}
        onDisable={onDisable}
      />,
    )

    const text = screen.getByTestId('pattern-suggestion-text')
    expect(text).toHaveTextContent('checks weather')
    expect(text).toHaveTextContent('starts a meeting')
  })

  it('renders Accept, Decline, and Disable buttons', () => {
    render(
      <PatternSuggestion
        suggestion={makeSuggestion()}
        onAccept={onAccept}
        onDecline={onDecline}
        onDisable={onDisable}
      />,
    )

    expect(screen.getByTestId('pattern-accept')).toBeInTheDocument()
    expect(screen.getByTestId('pattern-decline')).toBeInTheDocument()
    expect(screen.getByTestId('pattern-disable')).toBeInTheDocument()
  })

  it('calls onAccept with pattern_id and dismisses', () => {
    render(
      <PatternSuggestion
        suggestion={makeSuggestion({ pattern_id: 'pat-abc' })}
        onAccept={onAccept}
        onDecline={onDecline}
        onDisable={onDisable}
      />,
    )

    fireEvent.click(screen.getByTestId('pattern-accept'))
    expect(onAccept).toHaveBeenCalledWith('pat-abc')
    expect(screen.queryByTestId('pattern-suggestion')).not.toBeInTheDocument()
  })

  it('calls onDecline with pattern_id and dismisses', () => {
    render(
      <PatternSuggestion
        suggestion={makeSuggestion({ pattern_id: 'pat-dec' })}
        onAccept={onAccept}
        onDecline={onDecline}
        onDisable={onDisable}
      />,
    )

    fireEvent.click(screen.getByTestId('pattern-decline'))
    expect(onDecline).toHaveBeenCalledWith('pat-dec')
    expect(screen.queryByTestId('pattern-suggestion')).not.toBeInTheDocument()
  })

  it('calls onDisable with pattern_id and dismisses', () => {
    render(
      <PatternSuggestion
        suggestion={makeSuggestion({ pattern_id: 'pat-dis' })}
        onAccept={onAccept}
        onDecline={onDecline}
        onDisable={onDisable}
      />,
    )

    fireEvent.click(screen.getByTestId('pattern-disable'))
    expect(onDisable).toHaveBeenCalledWith('pat-dis')
    expect(screen.queryByTestId('pattern-suggestion')).not.toBeInTheDocument()
  })

  it('renders as a non-intrusive inline note (role=note, not a popup)', () => {
    render(
      <PatternSuggestion
        suggestion={makeSuggestion()}
        onAccept={onAccept}
        onDecline={onDecline}
        onDisable={onDisable}
      />,
    )

    const el = screen.getByTestId('pattern-suggestion')
    expect(el.getAttribute('role')).toBe('note')
  })
})
