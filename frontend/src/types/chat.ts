export type MessageRole = 'user' | 'assistant' | 'system'

export type MessageStatus = 'sending' | 'sent' | 'error' | 'done'

export interface ChatMessage {
  id: string
  role: MessageRole
  content: string
  timestamp: Date
  status: MessageStatus
  attachedFiles?: AttachedFile[]
}

export interface AttachedFile {
  name: string
  type: string
  size: number
  preview?: string // data URL for images
}

export interface UseChatReturn {
  messages: ChatMessage[]
  isStreaming: boolean
  streamingContent: string
  error: string | null
  conversationId: string | null
  sendMessage: (text: string, files?: AttachedFile[]) => Promise<void>
  retryLast: () => Promise<void>
  clearMessages: () => void
  loadConversation: (conv: { id: string; messages: Array<{ role: string; content: string }> }) => void
}

export interface ChatRequest {
  messages: ChatMessage[]
  provider?: string
  model?: string | null
  stream?: boolean
  conversation_id?: string | null
  profile_id?: string | null
}

export interface ChatResponse {
  provider: string
  model: string
  content: string
  conversation_id: string
}
