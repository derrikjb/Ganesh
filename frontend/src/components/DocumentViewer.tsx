import { useCallback, useEffect, useState } from 'react'
import type { OpenDocument } from '../types/documents'

interface DocumentViewerProps {
  document: OpenDocument
  onClose: () => void
  onNavigate: (direction: 'next' | 'prev') => void
  hasNext: boolean
  hasPrev: boolean
}

function ImageViewer({ content, name }: { content: string; name: string }) {
  const [zoom, setZoom] = useState(1)

  const zoomIn = useCallback(() => setZoom((z) => Math.min(z + 0.25, 3)), [])
  const zoomOut = useCallback(() => setZoom((z) => Math.max(z - 0.25, 0.25)), [])
  const resetZoom = useCallback(() => setZoom(1), [])

  return (
    <div className="flex flex-col items-center h-full">
      <div className="flex items-center gap-2 mb-2">
        <button
          onClick={zoomOut}
          className="px-2 py-1 text-xs bg-bg-tertiary rounded hover:bg-bg-elevated transition-colors text-text-primary"
          data-testid="zoom-out"
        >
          −
        </button>
        <span className="text-xs text-text-muted w-12 text-center">{Math.round(zoom * 100)}%</span>
        <button
          onClick={zoomIn}
          className="px-2 py-1 text-xs bg-bg-tertiary rounded hover:bg-bg-elevated transition-colors text-text-primary"
          data-testid="zoom-in"
        >
          +
        </button>
        <button
          onClick={resetZoom}
          className="px-2 py-1 text-xs bg-bg-tertiary rounded hover:bg-bg-elevated transition-colors text-text-primary"
          data-testid="zoom-reset"
        >
          Reset
        </button>
      </div>
      <div className="flex-1 overflow-auto w-full flex items-center justify-center">
        <img
          src={content}
          alt={name}
          style={{ transform: `scale(${zoom})`, transformOrigin: 'center center', transition: 'transform 150ms ease' }}
          className="max-w-full"
          data-testid="image-viewer"
        />
      </div>
    </div>
  )
}

function TextViewer({ content }: { content: string }) {
  return (
    <div className="h-full overflow-auto">
      <pre
        className="text-sm text-text-primary font-mono whitespace-pre-wrap p-4"
        data-testid="text-viewer"
      >
        {content}
      </pre>
    </div>
  )
}

function PdfViewer({ content }: { content: string }) {
  return (
    <div className="h-full">
      <iframe
        src={content}
        className="w-full h-full border-0"
        title="PDF Viewer"
        data-testid="pdf-viewer"
      />
    </div>
  )
}

function JsonViewer({ content }: { content: string }) {
  const [parsed, setParsed] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    try {
      const obj = JSON.parse(content)
      setParsed(JSON.stringify(obj, null, 2))
      setError(null)
    } catch {
      setParsed(null)
      setError('Invalid JSON')
    }
  }, [content])

  return (
    <div className="h-full overflow-auto">
      {error ? (
        <div className="p-4 text-status-error text-sm" data-testid="json-error">{error}</div>
      ) : (
        <pre
          className="text-sm text-text-primary font-mono p-4"
          data-testid="json-viewer"
        >
          {parsed}
        </pre>
      )}
    </div>
  )
}

function UnknownViewer({ name }: { name: string }) {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center">
        <span className="text-4xl mb-4 block">📎</span>
        <p className="text-text-secondary text-sm">Unsupported file type: {name}</p>
      </div>
    </div>
  )
}

export function DocumentViewer({ document: doc, onClose, onNavigate, hasNext, hasPrev }: DocumentViewerProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowRight' && hasNext) onNavigate('next')
      if (e.key === 'ArrowLeft' && hasPrev) onNavigate('prev')
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose, onNavigate, hasNext, hasPrev])

  const handleDownload = useCallback(() => {
    const link = globalThis.document.createElement('a')
    link.href = doc.content
    link.download = doc.name
    link.click()
  }, [doc.content, doc.name])

  const renderContent = () => {
    switch (doc.type) {
      case 'image':
        return <ImageViewer content={doc.content} name={doc.name} />
      case 'text':
        return <TextViewer content={doc.content} />
      case 'pdf':
        return <PdfViewer content={doc.content} />
      case 'json':
        return <JsonViewer content={doc.content} />
      default:
        return <UnknownViewer name={doc.name} />
    }
  }

  return (
    <div
      className="fixed inset-0 z-overlay flex items-center justify-center"
      data-testid="document-viewer-overlay"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-bg-primary/90" />
      <div
        className="relative w-[90vw] h-[90vh] bg-bg-secondary rounded-lg shadow-xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        data-testid="document-viewer"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-bg-primary">
          <div className="flex items-center gap-3 min-w-0">
            <h3 className="text-sm font-medium text-text-primary truncate">{doc.name}</h3>
            <span className="text-xs text-text-muted">{doc.type.toUpperCase()}</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleDownload}
              className="p-1.5 text-text-muted hover:text-text-primary transition-colors rounded"
              aria-label="Download"
              data-testid="download-button"
              title="Download"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
            </button>
            {hasPrev && (
              <button
                onClick={() => onNavigate('prev')}
                className="p-1.5 text-text-muted hover:text-text-primary transition-colors rounded"
                aria-label="Previous document"
                data-testid="prev-button"
                title="Previous"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="15 18 9 12 15 6" />
                </svg>
              </button>
            )}
            {hasNext && (
              <button
                onClick={() => onNavigate('next')}
                className="p-1.5 text-text-muted hover:text-text-primary transition-colors rounded"
                aria-label="Next document"
                data-testid="next-button"
                title="Next"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </button>
            )}
            <button
              onClick={onClose}
              className="p-1.5 text-text-muted hover:text-status-error transition-colors rounded"
              aria-label="Close"
              data-testid="close-button"
              title="Close (Esc)"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-hidden">
          {renderContent()}
        </div>
      </div>
    </div>
  )
}
