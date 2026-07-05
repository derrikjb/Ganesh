import type { ChatMessage as ChatMessageType } from '../types/chat'

interface ChatMessageProps {
  message: ChatMessageType
}

function formatTimestamp(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function renderMarkdownLike(content: string): string {
  let html = content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="chat-code-block"><code>$2</code></pre>')
  html = html.replace(/`([^`]+)`/g, '<code class="chat-inline-code">$1</code>')
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
  html = html.replace(/\n/g, '<br/>')

  return html
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user'

  return (
    <div
      className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}
      data-testid={`message-${message.role}`}
    >
      <div
        className={`max-w-[75%] rounded-lg px-4 py-3 ${
          isUser
            ? 'bg-accent text-text-inverse rounded-br-sm'
            : 'bg-bg-tertiary text-text-primary rounded-bl-sm'
        }`}
      >
        {message.attachedFiles && message.attachedFiles.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {message.attachedFiles.map((file, i) => (
              <div
                key={i}
                className="flex items-center gap-1 text-xs bg-bg-secondary rounded px-2 py-1"
              >
                {file.preview ? (
                  <img
                    src={file.preview}
                    alt={file.name}
                    className="w-8 h-8 object-cover rounded"
                  />
                ) : (
                  <span className="text-text-muted">[file]</span>
                )}
                <span className="truncate max-w-[120px]">{file.name}</span>
              </div>
            ))}
          </div>
        )}

        <div
          className="text-sm leading-relaxed"
          dangerouslySetInnerHTML={{ __html: renderMarkdownLike(message.content) }}
        />

        <div className={`flex items-center gap-2 mt-2 ${isUser ? 'justify-end' : 'justify-start'}`}>
          <span className={`text-xs ${isUser ? 'text-text-inverse/70' : 'text-text-muted'}`}>
            {formatTimestamp(message.timestamp)}
          </span>
          {message.status === 'error' && (
            <span className="text-xs text-status-error">Failed to send</span>
          )}
          {message.status === 'sending' && (
            <span className="text-xs text-text-muted">Sending...</span>
          )}
        </div>
      </div>
    </div>
  )
}
