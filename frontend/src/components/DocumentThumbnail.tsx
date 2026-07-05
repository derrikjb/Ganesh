import type { OpenDocument } from '../types/documents'

interface DocumentThumbnailProps {
  file: { name: string; type: string; size: number; preview?: string }
  onClick: () => void
}

function getFileIcon(type: string): string {
  if (type.startsWith('image/')) return '🖼'
  if (type === 'application/pdf') return '📄'
  if (type === 'application/json' || type.endsWith('.json')) return '📋'
  if (type.startsWith('text/')) return '📝'
  return '📎'
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function DocumentThumbnail({ file, onClick }: DocumentThumbnailProps) {
  const icon = getFileIcon(file.type)

  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 bg-bg-tertiary rounded-md px-2 py-1.5 hover:bg-bg-elevated transition-colors border border-border cursor-pointer"
      data-testid="document-thumbnail"
      title={file.name}
    >
      {file.preview ? (
        <img
          src={file.preview}
          alt={file.name}
          className="w-8 h-8 object-cover rounded"
        />
      ) : (
        <span className="text-lg" role="img" aria-label={file.type}>
          {icon}
        </span>
      )}
      <div className="flex flex-col items-start min-w-0">
        <span className="text-xs text-text-primary truncate max-w-[100px]">{file.name}</span>
        <span className="text-[10px] text-text-muted">{formatFileSize(file.size)}</span>
      </div>
    </button>
  )
}

export function DocumentThumbnailFromDoc({ doc, onClick }: { doc: OpenDocument; onClick: () => void }) {
  const icon = getDocIcon(doc.type)

  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 bg-bg-tertiary rounded-md px-2 py-1.5 hover:bg-bg-elevated transition-colors border border-border cursor-pointer"
      data-testid="document-thumbnail"
      title={doc.name}
    >
      {doc.type === 'image' ? (
        <img
          src={doc.content}
          alt={doc.name}
          className="w-8 h-8 object-cover rounded"
        />
      ) : (
        <span className="text-lg" role="img" aria-label={doc.type}>
          {icon}
        </span>
      )}
      <div className="flex flex-col items-start min-w-0">
        <span className="text-xs text-text-primary truncate max-w-[100px]">{doc.name}</span>
        <span className="text-[10px] text-text-muted">{formatFileSize(doc.size)}</span>
      </div>
    </button>
  )
}

function getDocIcon(type: OpenDocument['type']): string {
  switch (type) {
    case 'image': return '🖼'
    case 'pdf': return '📄'
    case 'json': return '📋'
    case 'text': return '📝'
    default: return '📎'
  }
}
