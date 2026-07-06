import { useState, useEffect } from 'react'

interface NaturalPacingIndicatorProps {
  isThinking: boolean
  isPacing: boolean
}

export function NaturalPacingIndicator({ isThinking, isPacing }: NaturalPacingIndicatorProps) {
  const [dots, setDots] = useState(0)

  useEffect(() => {
    if (!isThinking) {
      setDots(0)
      return
    }
    const interval = setInterval(() => {
      setDots((d) => (d + 1) % 4)
    }, 400)
    return () => clearInterval(interval)
  }, [isThinking])

  if (!isThinking && !isPacing) return null

  return (
    <div className="flex justify-start mb-4" data-testid="natural-pacing-indicator">
      <div className="bg-bg-tertiary rounded-lg rounded-bl-sm px-4 py-3">
        <div className="flex items-center gap-2">
          {isThinking && (
            <>
              <span className="text-xs text-text-muted">Ganesh is thinking</span>
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 bg-accent rounded-full animate-pulse" />
                <span className="w-1.5 h-1.5 bg-accent rounded-full animate-pulse" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-accent rounded-full animate-pulse" style={{ animationDelay: '300ms' }} />
              </div>
            </>
          )}
          {isPacing && (
            <>
              <span className="text-xs text-text-muted">Ganesh is typing</span>
              <span className="text-xs text-text-muted">{'.'.repeat(dots)}</span>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
