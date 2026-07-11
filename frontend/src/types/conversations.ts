export interface ConversationMessage {
  id: string
  role: string
  content: string
  created_at: string
}

export interface Checkpoint {
  id: string
  conversation_id: string
  sequence_number: number
  summary: string
  start_message_id: string | null
  end_message_id: string | null
  created_at: string
}

export interface ConversationSummary {
  id: string
  title: string
  profile_id: string | null
  created_at: string
  updated_at: string
  message_count: number
  summary: string | null
  status: string
  closed_at: string | null
}

export interface ConversationDetail extends ConversationSummary {
  messages: ConversationMessage[]
  checkpoints: Checkpoint[]
}

export type ExportFormat = 'json' | 'markdown'
