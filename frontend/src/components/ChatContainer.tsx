import { useCallback, useEffect, useRef, useState } from 'react'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { PatternSuggestion } from './PatternSuggestion'
import { NaturalPacingIndicator } from './NaturalPacing'
import { ThinkingIndicator } from './ThinkingIndicator'
import { useNaturalPacing } from '../hooks/useNaturalPacing'
import type { PatternSuggestionData } from './PatternSuggestion'
import { useChat } from '../hooks/useChat'
import { useAccessibility } from '../contexts/AccessibilityContext'
import { useVisualizerState } from '../contexts/VisualizerStateContext'
import { sidecarFetch } from '../api'
import type { ChatMessage as ChatMessageType } from '../types/chat'
import type { OpenDocument } from '../types/documents'

interface ChatContainerProps {
  documents: OpenDocument[]
  onOpenDocument: (file: { name: string; type: string; size: number; content: string }) => void
}

function StreamingIndicator() {
  return (
    <div className="flex justify-start mb-4" data-testid="streaming-indicator">
      <div className="bg-bg-tertiary rounded-lg rounded-bl-sm px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-xs text-text-muted">Ganesh is thinking</span>
          <div className="flex gap-1">
            <span className="w-1.5 h-1.5 bg-accent rounded-full animate-pulse" />
            <span className="w-1.5 h-1.5 bg-accent rounded-full animate-pulse" style={{ animationDelay: '150ms' }} />
            <span className="w-1.5 h-1.5 bg-accent rounded-full animate-pulse" style={{ animationDelay: '300ms' }} />
          </div>
        </div>
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center px-6" data-testid="empty-state">
      <div className="w-16 h-16 rounded-full bg-accent-muted flex items-center justify-center mb-4">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-accent">
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" />
          <path d="M8 14s1.5 2 4 2 4-2 4-2" />
          <line x1="9" y1="9" x2="9.01" y2="9" strokeWidth="3" strokeLinecap="round" />
          <line x1="15" y1="9" x2="15.01" y2="9" strokeWidth="3" strokeLinecap="round" />
        </svg>
      </div>
      <h2 className="text-xl font-semibold text-text-primary mb-2">Welcome to Ganesh</h2>
      <p className="text-text-secondary text-sm max-w-md">
        Your local AI assistant. Ask me anything, attach files for context, and I&apos;ll do my best to help.
      </p>
    </div>
  )
}

function ScrollToBottomButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-bg-elevated border border-border rounded-full p-2 shadow-md hover:bg-bg-tertiary transition-colors"
      aria-label="Scroll to bottom"
      data-testid="scroll-to-bottom"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>
  )
}

export function ChatContainer({ onOpenDocument }: ChatContainerProps) {
  const { messages, isStreaming, streamingContent, error, sendMessage, retryLast, loadConversation, clearMessages } = useChat()
  const { textOnlyMode, naturalPacingEnabled, naturalPacingSpeed } = useAccessibility()
  const { setState: setVisualizerState } = useVisualizerState()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  const [showScrollButton, setShowScrollButton] = useState(false)
  const [patternSuggestion, setPatternSuggestion] = useState<PatternSuggestionData | null>(null)
  const wasStreamingRef = useRef(false)

  const { pacedContent, isThinking, isPacing } = useNaturalPacing(streamingContent, isStreaming, {
    config: { enabled: naturalPacingEnabled, speedMultiplier: naturalPacingSpeed },
  })

  useEffect(() => {
    if (isStreaming) {
      setVisualizerState('THINKING')
    } else if (wasStreamingRef.current) {
      // SPEAKING→IDLE transition gives visualizer a natural wind-down
      setVisualizerState('SPEAKING')
      const timer = setTimeout(() => setVisualizerState('IDLE'), 500)
      return () => clearTimeout(timer)
    } else {
      setVisualizerState('IDLE')
    }
    wasStreamingRef.current = isStreaming
  }, [isStreaming, setVisualizerState])

  const fetchSuggestion = useCallback(async (context: string) => {
    if (!context.trim()) return
    try {
      const res = await sidecarFetch('/api/patterns/suggest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ context, limit: 1 }),
      })
      if (!res.ok) return
      const data = (await res.json()) as { suggestion: PatternSuggestionData | null }
      if (data.suggestion) {
        setPatternSuggestion(data.suggestion)
      }
    } catch {
      // Suggestion is non-critical; silently ignore errors.
    }
  }, [])

  const handleSuggestionAction = useCallback(
    async (action: 'accept' | 'decline' | 'disable', patternId: string) => {
      try {
        await sidecarFetch(`/api/patterns/${patternId}/${action}`, { method: 'POST' })
      } catch {
        // Best-effort; dismiss regardless.
      }
      setPatternSuggestion(null)
    },
    [],
  )

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as {
        id: string
        messages: Array<{ role: string; content: string }>
      }
      loadConversation(detail)
    }
    window.addEventListener('ganesh:load-conversation', handler)
    return () => window.removeEventListener('ganesh:load-conversation', handler)
  }, [loadConversation])

  useEffect(() => {
    const handler = () => clearMessages()
    window.addEventListener('ganesh:conversation-deleted', handler)
    return () => window.removeEventListener('ganesh:conversation-deleted', handler)
  }, [clearMessages])

  useEffect(() => {
    if (messagesEndRef.current && !showScrollButton) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, streamingContent, showScrollButton])

  useEffect(() => {
    const lastUser = [...messages].reverse().find((m) => m.role === 'user')
    if (lastUser && !isStreaming) {
      void fetchSuggestion(lastUser.content)
    }
  }, [messages, isStreaming, fetchSuggestion])

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 200
    setShowScrollButton(!isNearBottom)
  }, [])

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    setShowScrollButton(false)
  }, [])

  const displayMessages: ChatMessageType[] = messages.map((m) => {
    if (m.role === 'assistant' && m.id === messages[messages.length - 1]?.id && isStreaming) {
      return { ...m, content: naturalPacingEnabled ? pacedContent : streamingContent }
    }
    return m
  })

  return (
    <div className="flex flex-col h-full">
      {textOnlyMode && (
        <div
          className="px-4 py-2 bg-accent-muted border-b border-accent/30 text-xs text-accent"
          data-testid="text-only-banner"
          role="status"
        >
          Text-only mode active · voice features disabled
        </div>
      )}

      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-4 py-4"
        data-testid="message-list"
      >
        {displayMessages.length === 0 && !isStreaming ? (
          <EmptyState />
        ) : (
          <>
            {displayMessages.map((message) => (
              <ChatMessage key={message.id} message={message} onOpenDocument={onOpenDocument} />
            ))}
            {isStreaming && naturalPacingEnabled && <NaturalPacingIndicator isThinking={isThinking} isPacing={isPacing} />}
            {isStreaming && !naturalPacingEnabled && <StreamingIndicator />}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>

      {!textOnlyMode && (
        <div
          className="flex items-center justify-between px-4 py-1 border-t border-border bg-bg-secondary text-xs text-text-muted"
          data-testid="voice-controls"
        >
          <span className="flex items-center gap-2">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
              <path d="M19 10v2a7 7 0 01-14 0v-2" />
              <line x1="12" y1="19" x2="12" y2="23" />
            </svg>
            Voice I/O
          </span>
          <button
            className="text-text-muted hover:text-accent transition-colors"
            aria-label="Start voice input"
            data-testid="voice-input-button"
          >
            Press to speak
          </button>
        </div>
      )}

      {error && (
        <div className="px-4 py-2 bg-status-error/10 border-t border-status-error/20">
          <div className="flex items-center justify-between">
            <span className="text-xs text-status-error">{error}</span>
            <button
              onClick={retryLast}
              className="text-xs text-status-error hover:underline"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {patternSuggestion && (
        <PatternSuggestion
          suggestion={patternSuggestion}
          onAccept={(id) => void handleSuggestionAction('accept', id)}
          onDecline={(id) => void handleSuggestionAction('decline', id)}
          onDisable={(id) => void handleSuggestionAction('disable', id)}
        />
      )}

      <div className="relative px-4 py-3 border-t border-border bg-bg-primary">
        <ThinkingIndicator visible={isStreaming} />
        <ChatInput onSend={sendMessage} disabled={isStreaming} />
        {showScrollButton && <ScrollToBottomButton onClick={scrollToBottom} />}
      </div>
    </div>
  )
}
