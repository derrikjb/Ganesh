export type DocumentType = 'image' | 'text' | 'pdf' | 'json' | 'unknown'

export interface OpenDocument {
  id: string
  name: string
  type: DocumentType
  content: string // data URL for images, text content for text/json/pdf
  size: number
}

export interface UseDocumentsReturn {
  documents: OpenDocument[]
  activeDocument: OpenDocument | null
  openDocument: (file: { name: string; type: string; size: number; content: string }) => void
  closeDocument: (id?: string) => void
  navigateDocument: (direction: 'next' | 'prev') => void
}
