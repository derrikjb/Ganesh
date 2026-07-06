import { useCallback, useEffect, useRef, useState } from 'react'
import { sidecarFetch } from '../api'
import type { AttachedFile, ChatMessage, MessageStatus, UseChatReturn } from '../types/chat'

const MESSAGES_STORAGE_KEY = 'ganesh_chat_messages'
const CONVERSATION_STORAGE_KEY = 'ganesh_chat_conversation_id'

let messageIdCounter = 0
function generateId(): string {
  return `msg-${Date.now()}-${++messageIdCounter}`
}

function formatTime(date: Date): Date {
  return new Date(date)
}

function loadPersistedMessages(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(MESSAGES_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as ChatMessage[]
    if (!Array.isArray(parsed)) return []
    return parsed.filter((m) => m && m.id && m.role && typeof m.content === 'string')
  } catch {
    return []
  }
}

function loadPersistedConversationId(): string | null {
  try {
    return localStorage.getItem(CONVERSATION_STORAGE_KEY) || null
  } catch {
    return null
  }
}

function persistMessages(messages: ChatMessage[]): void {
  try {
    const serializable = messages
      .filter((m) => m.status !== 'sending' && m.status !== 'error')
      .map((m) => ({
        ...m,
        attachedFiles: m.attachedFiles?.map((f) => ({ ...f, content: '' })),
      }))
    localStorage.setItem(MESSAGES_STORAGE_KEY, JSON.stringify(serializable))
  } catch {
  }
}

function persistConversationId(id: string | null): void {
  try {
    if (id) {
      localStorage.setItem(CONVERSATION_STORAGE_KEY, id)
    } else {
      localStorage.removeItem(CONVERSATION_STORAGE_KEY)
    }
  } catch {
  }
}

async function safeJson<T>(res: Response): Promise<T | null> {
  try {
    return (await res.json()) as T
  } catch {
    return null
  }
}

async function ensureConversation(existingId: string | null): Promise<string | null> {
  if (existingId) return existingId
  try {
    const res = await sidecarFetch('/api/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: null }),
    })
    if (!res.ok) return null
    const data = await safeJson<{ id: string }>(res)
    return data?.id ?? null
  } catch {
    return null
  }
}

async function persistMessage(
  conversationId: string | null,
  role: string,
  content: string,
): Promise<void> {
  if (!conversationId || !content) return
  try {
    await sidecarFetch(`/api/conversations/${conversationId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role, content }),
    })
  } catch {
  }
}

export function useChat(): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadPersistedMessages())
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [conversationId, setConversationId] = useState<string | null>(() => loadPersistedConversationId())
  const abortRef = useRef<AbortController | null>(null)
  const lastUserMessageRef = useRef<string | null>(null)
  const lastFilesRef = useRef<AttachedFile[] | undefined>(undefined)
  const conversationIdRef = useRef<string | null>(loadPersistedConversationId())

  useEffect(() => {
    persistMessages(messages)
  }, [messages])

  useEffect(() => {
    persistConversationId(conversationId)
  }, [conversationId])

  const updateConversationId = useCallback((id: string | null) => {
    conversationIdRef.current = id
    setConversationId(id)
  }, [])

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

    const convId = await ensureConversation(conversationIdRef.current)
    if (convId && convId !== conversationIdRef.current) {
      updateConversationId(convId)
    }
    void persistMessage(convId, 'user', text)

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
      void persistMessage(convId, 'assistant', accumulated)
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
  }, [messages, updateConversationId])

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
    updateConversationId(null)
    abortRef.current?.abort()
  }, [updateConversationId])

  const loadConversation = useCallback(
    (conv: { id: string; messages: Array<{ role: string; content: string }> }) => {
      updateConversationId(conv.id)
      const loaded: ChatMessage[] = conv.messages.map((m, i) => ({
        id: `loaded-${conv.id}-${i}`,
        role: m.role as ChatMessage['role'],
        content: m.content,
        timestamp: new Date(),
        status: 'done' as MessageStatus,
      }))
      setMessages(loaded)
      setError(null)
      lastUserMessageRef.current = null
      lastFilesRef.current = undefined
    },
    [updateConversationId],
  )

  return {
    messages,
    isStreaming,
    streamingContent,
    error,
    conversationId,
    sendMessage,
    retryLast,
    clearMessages,
    loadConversation,
  }
}
