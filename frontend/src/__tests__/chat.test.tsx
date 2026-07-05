import '@testing-library/jest-dom'
import '@testing-library/jest-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, renderHook, cleanup } from '@testing-library/react'
import { ChatMessage } from '../components/ChatMessage'
import { ChatInput } from '../components/ChatInput'
import { AccessibilityProvider } from '../contexts/AccessibilityContext'
import type { ChatMessage as ChatMessageType, AttachedFile } from '../types/chat'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('../api', () => ({
  sidecarFetch: vi.fn(),
  getSidecarPort: vi.fn(),
}))

import { sidecarFetch } from '../api'

const mockSidecarFetch = sidecarFetch as ReturnType<typeof vi.fn>

function renderChatInput(props: { onSend: typeof vi.fn; disabled: boolean }) {
  return render(
    <AccessibilityProvider>
      <ChatInput onSend={props.onSend} disabled={props.disabled} />
    </AccessibilityProvider>,
  )
}

function makeMessage(overrides: Partial<ChatMessageType> = {}): ChatMessageType {
  return {
    id: 'test-1',
    role: 'user',
    content: 'Hello',
    timestamp: new Date('2024-01-01T12:00:00Z'),
    status: 'done',
    ...overrides,
  }
}

describe('ChatMessage', () => {
  afterEach(() => {
    cleanup()
  })

  it('renders user message right-aligned with accent background', () => {
    const userMsg = makeMessage({ role: 'user', content: 'User says hi' })
    render(<ChatMessage message={userMsg} />)

    const container = screen.getByTestId('message-user')
    expect(container).toBeInTheDocument()
    expect(container).toHaveClass('justify-end')
    expect(screen.getByText('User says hi')).toBeInTheDocument()
  })

  it('renders assistant message left-aligned with secondary background', () => {
    const assistantMsg = makeMessage({ role: 'assistant', content: 'Assistant replies' })
    render(<ChatMessage message={assistantMsg} />)

    const container = screen.getByTestId('message-assistant')
    expect(container).toBeInTheDocument()
    expect(container).toHaveClass('justify-start')
    expect(screen.getByText('Assistant replies')).toBeInTheDocument()
  })

  it('renders timestamp', () => {
    const msg = makeMessage({ content: 'Test' })
    render(<ChatMessage message={msg} />)

    const timestamp = screen.getByText(/AM|PM|\d{2}:\d{2}/)
    expect(timestamp).toBeInTheDocument()
  })

  it('renders bold and code formatting', () => {
    const msg = makeMessage({ content: '**bold** and `code`' })
    render(<ChatMessage message={msg} />)

    expect(screen.getByText(/bold/).tagName).toBe('STRONG')
    expect(screen.getByText('code').tagName).toBe('CODE')
  })

  it('shows error status', () => {
    const msg = makeMessage({ status: 'error' })
    render(<ChatMessage message={msg} />)

    expect(screen.getByText('Failed to send')).toBeInTheDocument()
  })

  it('shows attached file previews', () => {
    const files: AttachedFile[] = [
      { name: 'test.png', type: 'image/png', size: 1000, preview: 'data:image/png;base64,abc' },
    ]
    const msg = makeMessage({ content: 'Here is a file', attachedFiles: files })
    render(<ChatMessage message={msg} />)

    expect(screen.getByText('test.png')).toBeInTheDocument()
  })
})

describe('ChatInput', () => {
  const mockOnSend = vi.fn()

  beforeEach(() => {
    mockOnSend.mockClear()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders textarea and send button', () => {
    renderChatInput({ onSend: mockOnSend, disabled: false })

    expect(screen.getByTestId('chat-textarea')).toBeInTheDocument()
    expect(screen.getByTestId('send-button')).toBeInTheDocument()
  })

  it('triggers send on button click', () => {
    renderChatInput({ onSend: mockOnSend, disabled: false })

    const textarea = screen.getByTestId('chat-textarea')
    fireEvent.change(textarea, { target: { value: 'Hello world' } })

    const sendBtn = screen.getByTestId('send-button')
    fireEvent.click(sendBtn)

    expect(mockOnSend).toHaveBeenCalledWith('Hello world', undefined)
  })

  it('triggers send on Ctrl+Enter', () => {
    renderChatInput({ onSend: mockOnSend, disabled: false })

    const textarea = screen.getByTestId('chat-textarea')
    fireEvent.change(textarea, { target: { value: 'Ctrl+Enter test' } })
    fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true })

    expect(mockOnSend).toHaveBeenCalledWith('Ctrl+Enter test', undefined)
  })

  it('triggers send on Meta+Enter', () => {
    renderChatInput({ onSend: mockOnSend, disabled: false })

    const textarea = screen.getByTestId('chat-textarea')
    fireEvent.change(textarea, { target: { value: 'Meta+Enter test' } })
    fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true })

    expect(mockOnSend).toHaveBeenCalledWith('Meta+Enter test', undefined)
  })

  it('does not send when disabled', () => {
    renderChatInput({ onSend: mockOnSend, disabled: true })

    const textarea = screen.getByTestId('chat-textarea')
    fireEvent.change(textarea, { target: { value: 'Should not send' } })

    const sendBtn = screen.getByTestId('send-button')
    fireEvent.click(sendBtn)

    expect(mockOnSend).not.toHaveBeenCalled()
  })

  it('does not send empty text', () => {
    renderChatInput({ onSend: mockOnSend, disabled: false })

    const sendBtn = screen.getByTestId('send-button')
    fireEvent.click(sendBtn)

    expect(mockOnSend).not.toHaveBeenCalled()
  })

  it('handles file drop', () => {
    renderChatInput({ onSend: mockOnSend, disabled: false })

    const dropzone = screen.getByTestId('chat-textarea').parentElement!
    const file = new File(['test content'], 'test.txt', { type: 'text/plain' })
    const dataTransfer = { files: [file] } as unknown as DataTransfer

    fireEvent.drop(dropzone, { dataTransfer })

    expect(screen.getByText('test.txt')).toBeInTheDocument()
  })

  it('sends with attached files', () => {
    renderChatInput({ onSend: mockOnSend, disabled: false })

    const dropzone = screen.getByTestId('chat-textarea').parentElement!
    const file = new File(['test content'], 'test.txt', { type: 'text/plain' })
    const dataTransfer = { files: [file] } as unknown as DataTransfer
    fireEvent.drop(dropzone, { dataTransfer })

    const textarea = screen.getByTestId('chat-textarea')
    fireEvent.change(textarea, { target: { value: 'With file' } })

    const sendBtn = screen.getByTestId('send-button')
    fireEvent.click(sendBtn)

    expect(mockOnSend).toHaveBeenCalled()
    const callArgs = mockOnSend.mock.calls[0]
    expect(callArgs[0]).toBe('With file')
    expect(callArgs[1]).toBeDefined()
    expect(callArgs[1][0].name).toBe('test.txt')
  })
})

describe('Chat streaming', () => {
  beforeEach(() => {
    mockSidecarFetch.mockReset()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('accumulates streaming content correctly', async () => {
    const mockReader = {
      read: vi.fn()
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('data: {"content": "Hello"}\n\n'),
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('data: {"content": " World"}\n\n'),
        })
        .mockResolvedValueOnce({
          done: false,
          value: new TextEncoder().encode('event: done\ndata: {"done": true}\n\n'),
        })
        .mockResolvedValueOnce({ done: true, value: undefined }),
    }

    mockSidecarFetch.mockResolvedValue({
      ok: true,
      body: { getReader: () => mockReader },
    })

    const { useChat } = await import('../hooks/useChat')
    const { result } = renderHook(() => useChat())

    await result.current.sendMessage('Test')

    await waitFor(() => {
      const messages = result.current.messages
      const assistantMsg = messages.find((m) => m.role === 'assistant')
      expect(assistantMsg?.content).toBe('Hello World')
      expect(assistantMsg?.status).toBe('done')
    }, { timeout: 3000 })
  })
})
