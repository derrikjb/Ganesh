import { useCallback, useState } from 'react'
import type { OpenDocument, UseDocumentsReturn } from '../types/documents'

let docIdCounter = 0
function generateDocId(): string {
  return `doc-${Date.now()}-${++docIdCounter}`
}

export function useDocuments(): UseDocumentsReturn {
  const [documents, setDocuments] = useState<OpenDocument[]>([])
  const [activeIndex, setActiveIndex] = useState<number | null>(null)

  const openDocument = useCallback((file: { name: string; type: string; size: number; content: string }) => {
    setDocuments((prev) => {
      const existing = prev.find((d) => d.name === file.name && d.content === file.content)
      if (existing) {
        setActiveIndex(prev.indexOf(existing))
        return prev
      }

      const docType = getDocumentType(file.type, file.name)
      const newDoc: OpenDocument = {
        id: generateDocId(),
        name: file.name,
        type: docType,
        content: file.content,
        size: file.size,
      }

      setActiveIndex(prev.length)
      return [...prev, newDoc]
    })
  }, [])

  const closeDocument = useCallback((id?: string) => {
    if (id) {
      setDocuments((prev) => {
        const idx = prev.findIndex((d) => d.id === id)
        const filtered = prev.filter((d) => d.id !== id)
        if (activeIndex !== null) {
          if (idx === activeIndex) {
            setActiveIndex(filtered.length > 0 ? Math.min(idx, filtered.length - 1) : null)
          } else if (idx < activeIndex) {
            setActiveIndex(activeIndex - 1)
          }
        }
        return filtered
      })
    } else {
      setDocuments([])
      setActiveIndex(null)
    }
  }, [activeIndex])

  const navigateDocument = useCallback((direction: 'next' | 'prev') => {
    if (activeIndex === null || documents.length === 0) return
    const newIndex = direction === 'next'
      ? Math.min(activeIndex + 1, documents.length - 1)
      : Math.max(activeIndex - 1, 0)
    setActiveIndex(newIndex)
  }, [activeIndex, documents.length])

  const activeDocument = activeIndex !== null ? documents[activeIndex] ?? null : null

  return { documents, activeDocument, openDocument, closeDocument, navigateDocument }
}

function getDocumentType(mimeType: string, fileName: string): 'image' | 'text' | 'pdf' | 'json' | 'unknown' {
  if (mimeType.startsWith('image/')) return 'image'
  if (mimeType === 'application/pdf') return 'pdf'
  if (mimeType === 'application/json' || fileName.endsWith('.json')) return 'json'
  if (mimeType.startsWith('text/')) return 'text'
  if (fileName.endsWith('.txt') || fileName.endsWith('.md') || fileName.endsWith('.csv')) return 'text'
  return 'unknown'
}
