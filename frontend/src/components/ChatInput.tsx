import { useCallback, useEffect, useRef, useState } from 'react'
import { listen } from '@tauri-apps/api/event'
import { sidecarFetch } from '../api'
import { useAccessibility } from '../contexts/AccessibilityContext'
import { useVoiceRecording } from '../hooks/useVoiceRecording'
import type { AttachedFile } from '../types/chat'

type ActivationMode = 'click_to_talk' | 'push_to_talk' | 'vad'

interface ChatInputProps {
  onSend: (text: string, files?: AttachedFile[]) => void
  disabled: boolean
}

const ACCEPTED_TYPES = ['image/*', 'text/*', 'application/pdf']

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const { textOnlyMode } = useAccessibility()
  const [text, setText] = useState('')
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [justSent, setJustSent] = useState(false)
  const [activationMode, setActivationMode] = useState<ActivationMode>('click_to_talk')
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { isRecording, isTranscribing, transcript, error, start, stop, resetTranscript } =
    useVoiceRecording()

  useEffect(() => {
    if (transcript) {
      setText(transcript)
      resetTranscript()
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
        textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`
      }
    }
  }, [transcript, resetTranscript])

  useEffect(() => {
    sidecarFetch('/api/voice/settings')
      .then((res) => res.json())
      .then((data) => {
        if (data.activation_mode) {
          setActivationMode(data.activation_mode)
          if (import.meta.env.DEV) console.log('[PTT] activation mode:', data.activation_mode)
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    const handler = (e: Event) => {
      const mode = (e as CustomEvent<ActivationMode>).detail
      if (mode) setActivationMode(mode)
    }
    window.addEventListener('ganesh:activation-mode-changed', handler)
    return () => window.removeEventListener('ganesh:activation-mode-changed', handler)
  }, [])

  const pttActiveRef = useRef(false)

  useEffect(() => {
    if (activationMode !== 'push_to_talk') {
      if (import.meta.env.DEV) console.log('[PTT] skipping listener setup, mode is:', activationMode)
      return
    }

    let pressUnlisten: (() => void) | null = null
    let releaseUnlisten: (() => void) | null = null
    let cancelled = false

    if (import.meta.env.DEV) console.log('[PTT] setting up listeners for push_to_talk')

    listen('ganesh:ptt-press', () => {
      if (import.meta.env.DEV) console.log('[PTT] press event received, active:', pttActiveRef.current)
      if (!pttActiveRef.current && !isTranscribing) {
        pttActiveRef.current = true
        void start()
      }
    }).then((fn) => {
      if (cancelled) { fn(); return }
      pressUnlisten = fn
      if (import.meta.env.DEV) console.log('[PTT] press listener ready')
    }).catch((err) => {
      if (import.meta.env.DEV) console.error('[PTT] failed to listen for press:', err)
    })

    listen('ganesh:ptt-release', () => {
      if (import.meta.env.DEV) console.log('[PTT] release event received, active:', pttActiveRef.current)
      if (pttActiveRef.current) {
        pttActiveRef.current = false
        void stop()
      }
    }).then((fn) => {
      if (cancelled) { fn(); return }
      releaseUnlisten = fn
      if (import.meta.env.DEV) console.log('[PTT] release listener ready')
    }).catch((err) => {
      if (import.meta.env.DEV) console.error('[PTT] failed to listen for release:', err)
    })

    return () => {
      cancelled = true
      pressUnlisten?.()
      releaseUnlisten?.()
    }
  }, [activationMode, isTranscribing, start, stop])

  const handleFileSelect = useCallback((fileList: FileList) => {
    const files: AttachedFile[] = []
    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i]
      const attached: AttachedFile = {
        name: file.name,
        type: file.type,
        size: file.size,
      }
      if (file.type.startsWith('image/')) {
        const reader = new FileReader()
        reader.onload = (e) => {
          attached.preview = e.target?.result as string
          setAttachedFiles((prev) => {
            const updated = [...prev]
            updated[i] = attached
            return updated
          })
        }
        reader.readAsDataURL(file)
      }
      files.push(attached)
    }
    setAttachedFiles((prev) => [...prev, ...files])
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      if (e.dataTransfer.files.length > 0) {
        handleFileSelect(e.dataTransfer.files)
      }
    },
    [handleFileSelect],
  )

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleSend = useCallback(() => {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed, attachedFiles.length > 0 ? attachedFiles : undefined)
    setText('')
    setAttachedFiles([])
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
    setJustSent(true)
    window.setTimeout(() => setJustSent(false), 1200)
  }, [text, attachedFiles, disabled, onSend])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        handleSend()
      }
    },
    [handleSend],
  )

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [])

  const removeFile = useCallback((index: number) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index))
  }, [])

  return (
    <div className="relative">
      {attachedFiles.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2 px-2">
          {attachedFiles.map((file, i) => (
            <div
              key={i}
              className="relative flex items-center gap-2 bg-bg-tertiary rounded-md px-2 py-1 pr-6"
            >
              {file.preview ? (
                <img src={file.preview} alt={file.name} className="w-10 h-10 object-cover rounded" />
              ) : (
                <div className="w-10 h-10 bg-bg-secondary rounded flex items-center justify-center">
                  <span className="text-xs text-text-muted">[file]</span>
                </div>
              )}
              <span className="text-xs text-text-secondary truncate max-w-[100px]">{file.name}</span>
              <button
                onClick={() => removeFile(i)}
                className="absolute top-0 right-0 text-text-muted hover:text-status-error text-xs px-1"
                aria-label={`Remove ${file.name}`}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <div
        className={`flex items-end gap-2 p-3 bg-bg-secondary rounded-lg border transition-colors ${
          isDragging ? 'border-accent bg-accent-muted' : 'border-border'
        }`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          placeholder="Type a message... (Ctrl+Enter to send)"
          disabled={disabled}
          rows={1}
          className="flex-1 bg-transparent text-text-primary text-sm resize-none outline-none placeholder:text-text-muted min-h-[24px] max-h-[200px]"
          data-testid="chat-textarea"
        />
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPTED_TYPES.join(',')}
          onChange={(e) => e.target.files && handleFileSelect(e.target.files)}
          className="hidden"
          aria-label="Attach files"
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          className="text-text-muted hover:text-text-primary transition-colors p-1"
          aria-label="Attach file"
          title="Attach file"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
          </svg>
        </button>
        {!textOnlyMode && (
          <button
            type="button"
            onClick={
              activationMode === 'push_to_talk'
                ? undefined
                : () => {
                    if (isTranscribing) return
                    if (isRecording) {
                      void stop()
                    } else {
                      void start()
                    }
                  }
            }
            onPointerDown={
              activationMode === 'push_to_talk'
                ? () => {
                    if (isTranscribing || isRecording) return
                    void start()
                  }
                : undefined
            }
            onPointerUp={
              activationMode === 'push_to_talk'
                ? () => {
                    if (isRecording) void stop()
                  }
                : undefined
            }
            onPointerLeave={
              activationMode === 'push_to_talk'
                ? () => {
                    if (isRecording) void stop()
                  }
                : undefined
            }
            disabled={disabled || isTranscribing}
            className={`p-1 transition-colors disabled:opacity-50 ${
              isRecording
                ? 'text-status-error animate-pulse'
                : 'text-text-muted hover:text-accent'
            }`}
            aria-label={
              activationMode === 'push_to_talk'
                ? 'Hold to talk'
                : activationMode === 'vad'
                  ? 'Auto-detect voice'
                  : isRecording
                    ? 'Stop recording'
                    : 'Click to talk'
            }
            title={
              isTranscribing
                ? 'Transcribing...'
                : activationMode === 'push_to_talk'
                  ? 'Hold to talk'
                  : activationMode === 'vad'
                    ? 'Auto-detect voice'
                    : isRecording
                      ? 'Stop recording'
                      : 'Click to talk'
            }
            data-testid="mic-button"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
              <path d="M19 10v2a7 7 0 01-14 0v-2" />
              <line x1="12" y1="19" x2="12" y2="23" />
              <line x1="8" y1="23" x2="16" y2="23" />
            </svg>
          </button>
        )}
        <button
          onClick={handleSend}
          disabled={disabled || !text.trim()}
          className={`p-2 rounded-md transition-colors ${
            disabled || !text.trim()
              ? 'text-text-muted cursor-not-allowed'
              : 'bg-accent text-text-inverse hover:bg-accent-hover'
          }`}
          data-testid="send-button"
          aria-label="Send message"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="22" y1="2" x2="11" y2="13" />
            <polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>

      {justSent && (
        <div
          className="absolute -top-6 right-4 text-xs text-status-success bg-bg-elevated px-2 py-1 rounded-md shadow-md"
          data-testid="send-confirmation"
          role="status"
        >
          Sent
        </div>
      )}

      {(isRecording || isTranscribing) && (
        <div
          className="absolute -top-6 right-4 text-xs text-status-error bg-bg-elevated px-2 py-1 rounded-md shadow-md flex items-center gap-1.5"
          data-testid="recording-indicator"
          role="status"
        >
          <span className="w-2 h-2 rounded-full bg-status-error animate-pulse" />
          {isTranscribing ? 'Transcribing...' : 'Recording...'}
        </div>
      )}

      {error && (
        <div
          className="absolute -top-6 left-4 text-xs text-status-error bg-bg-elevated px-2 py-1 rounded-md shadow-md"
          data-testid="voice-error"
          role="alert"
        >
          {error}
        </div>
      )}

      {isDragging && (
        <div className="absolute inset-0 flex items-center justify-center bg-accent-muted rounded-lg border-2 border-dashed border-accent pointer-events-none">
          <span className="text-accent text-sm font-medium">Drop files here</span>
        </div>
      )}
    </div>
  )
}
