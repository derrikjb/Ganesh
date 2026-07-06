import { useAccessibility } from '../contexts/AccessibilityContext'

interface ThinkingIndicatorProps {
  visible: boolean
}

export function ThinkingIndicator({ visible }: ThinkingIndicatorProps) {
  const { showThinkingIndicator } = useAccessibility()

  if (!visible || !showThinkingIndicator) {
    return null
  }

  return (
    <div
      className="flex items-center justify-center gap-1.5 py-1"
      data-testid="thinking-indicator"
      role="status"
      aria-live="polite"
    >
      <span className="text-xs text-text-muted">Ganesh is thinking</span>
      <div className="flex gap-1">
        <span className="w-1 h-1 bg-accent/60 rounded-full animate-pulse" />
        <span className="w-1 h-1 bg-accent/60 rounded-full animate-pulse" style={{ animationDelay: '200ms' }} />
        <span className="w-1 h-1 bg-accent/60 rounded-full animate-pulse" style={{ animationDelay: '400ms' }} />
      </div>
    </div>
  )
}
