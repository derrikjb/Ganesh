import { useCallback, useRef, useState } from 'react'
import { sidecarFetch } from '../api'
import type { AttachedFile, ChatMessage, MessageStatus, UseChatReturn } from '../types/chat'

let messageIdCounter = 0
function generateId(): string {
  return `msg-${Date.now()}-${++messageIdCounter}`
}

function formatTime(date: Date): Date {
  return new Date(date)
}

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const lastUserMessageRef = useRef<string | null>(null)
  const lastFilesRef = useRef<AttachedFile[] | undefined>(undefined)

  const sendMessage = useCallback(async (text: string, files?: AttachedFile[]) => {
    setError(null)
    lastUserMessageRef.current = text
    lastFilesRef.current = files

    const userMessage: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: text,
      timestamp: formatTime(new Date()),
      status: 'sending',
      attachedFiles: files,
    }

    setMessages((prev) => [...prev, userMessage])
    setIsStreaming(true)
    setStreamingContent('')

    const assistantId = generateId()
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: formatTime(new Date()),
      status: 'sending',
    }
    setMessages((prev) => [...prev, assistantMessage])

    const apiMessages = messages
      .filter((m) => m.role !== 'system')
      .map((m) => ({ role: m.role, content: m.content }))
    apiMessages.push({ role: 'user' as const, content: text })

    try {
      const controller = new AbortController()
      abortRef.current = controller

      const response = await sidecarFetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: apiMessages, stream: true }),
        signal: controller.signal,
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('No response body')
      }

      const decoder = new TextDecoder()
      let buffer = ''
      let accumulated = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('event: done')) {
            break
          }
          if (line.startsWith('event: error')) {
            continue
          }
          if (line.startsWith('data: ')) {
            try {
              const json = JSON.parse(line.slice(6))
              if (json.done) break
              if (json.content) {
                accumulated += json.content
                setStreamingContent(accumulated)
              }
            } catch {
              // skip malformed JSON
            }
          }
        }
      }

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: accumulated, status: 'done' as MessageStatus }
            : m.id === userMessage.id
              ? { ...m, status: 'sent' as MessageStatus }
              : m,
        ),
      )
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return

      const message = err instanceof Error ? err.message : 'Unknown error'
      setError(message)

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId || m.id === userMessage.id
            ? { ...m, status: 'error' as MessageStatus }
            : m,
        ),
      )
    } finally {
      setIsStreaming(false)
      setStreamingContent('')
      abortRef.current = null
    }
  }, [messages])

  const retryLast = useCallback(async () => {
    if (lastUserMessageRef.current) {
      setMessages((prev) => prev.filter((m) => m.status !== 'error'))
      await sendMessage(lastUserMessageRef.current, lastFilesRef.current)
    }
  }, [sendMessage])

  const clearMessages = useCallback(() => {
    setMessages([])
    setError(null)
    setStreamingContent('')
    setIsStreaming(false)
    lastUserMessageRef.current = null
    lastFilesRef.current = undefined
    abortRef.current?.abort()
  }, [])

  return { messages, isStreaming, streamingContent, error, sendMessage, retryLast, clearMessages }
}
