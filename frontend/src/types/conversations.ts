export interface ConversationMessage {
  id: string
  role: string
  content: string
  created_at: string
}

export interface ConversationSummary {
  id: string
  title: string
  profile_id: string | null
  created_at: string
  updated_at: string
  message_count: number
}

export interface ConversationDetail extends ConversationSummary {
  messages: ConversationMessage[]
}

export type ExportFormat = 'json' | 'markdown'
