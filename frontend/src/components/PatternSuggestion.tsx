import { useState } from 'react'

export interface PatternSuggestionData {
  pattern_id: string
  trigger: string
  followup: string
  confidence: number
  note: string
}

interface PatternSuggestionProps {
  suggestion: PatternSuggestionData
  onAccept: (patternId: string) => void
  onDecline: (patternId: string) => void
  onDisable: (patternId: string) => void
}

export function PatternSuggestion({
  suggestion,
  onAccept,
  onDecline,
  onDisable,
}: PatternSuggestionProps) {
  const [dismissed, setDismissed] = useState(false)

  if (dismissed) return null

  const handleAccept = () => {
    onAccept(suggestion.pattern_id)
    setDismissed(true)
  }
  const handleDecline = () => {
    onDecline(suggestion.pattern_id)
    setDismissed(true)
  }
  const handleDisable = () => {
    onDisable(suggestion.pattern_id)
    setDismissed(true)
  }

  return (
    <div
      className="mx-4 my-2 px-3 py-2 rounded-lg border border-accent/30 bg-accent-muted/40 text-xs text-text-secondary"
      data-testid="pattern-suggestion"
      role="note"
    >
      <div className="flex items-start gap-2">
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className="text-accent mt-0.5 shrink-0"
          aria-hidden="true"
        >
          <path d="M12 2L2 7l10 5 10-5-10-5z" />
          <path d="M2 17l10 5 10-5" />
          <path d="M2 12l10 5 10-5" />
        </svg>
        <div className="flex-1 min-w-0">
          <p className="text-text-primary" data-testid="pattern-suggestion-text">
            I notice you usually{' '}
            <span className="font-medium">{suggestion.trigger}</span> before{' '}
            <span className="font-medium">{suggestion.followup}</span>. Should I
            help with that?
          </p>
          <div className="flex items-center gap-2 mt-1.5">
            <button
              onClick={handleAccept}
              className="px-2 py-0.5 rounded bg-accent text-bg-primary text-xs font-medium hover:opacity-90 transition-opacity"
              data-testid="pattern-accept"
            >
              Yes
            </button>
            <button
              onClick={handleDecline}
              className="px-2 py-0.5 rounded border border-border text-text-secondary text-xs hover:bg-bg-tertiary transition-colors"
              data-testid="pattern-decline"
            >
              Not now
            </button>
            <button
              onClick={handleDisable}
              className="px-2 py-0.5 text-text-muted text-xs hover:text-text-secondary transition-colors underline-offset-2 hover:underline"
              data-testid="pattern-disable"
            >
              Don&apos;t suggest again
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
