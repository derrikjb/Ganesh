import '@testing-library/jest-dom'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DocumentThumbnail } from '../components/DocumentThumbnail'
import { DocumentViewer } from '../components/DocumentViewer'
import { useDocuments } from '../hooks/useDocuments'
import { renderHook, act } from '@testing-library/react'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('../api', () => ({
  sidecarFetch: vi.fn(),
  getSidecarPort: vi.fn(),
}))

describe('DocumentThumbnail', () => {
  const mockFile = {
    name: 'test.png',
    type: 'image/png',
    size: 1024,
  }

  it('formats file sizes correctly', () => {
    const { rerender } = render(<DocumentThumbnail file={{ ...mockFile, size: 500 }} onClick={() => {}} />)
    expect(screen.getByText('500 B')).toBeInTheDocument()

    rerender(<DocumentThumbnail file={{ ...mockFile, size: 1536 }} onClick={() => {}} />)
    expect(screen.getByText('1.5 KB')).toBeInTheDocument()

    rerender(<DocumentThumbnail file={{ ...mockFile, size: 3 * 1024 * 1024 }} onClick={() => {}} />)
    expect(screen.getByText('3.0 MB')).toBeInTheDocument()
  })
})

describe('DocumentViewer', () => {
  const mockImageDoc = {
    id: 'doc-1',
    name: 'photo.png',
    type: 'image' as const,
    content: 'data:image/png;base64,fakeimage',
    size: 2048,
  }

  const mockTextDoc = {
    id: 'doc-2',
    name: 'notes.txt',
    type: 'text' as const,
    content: 'Hello world\nThis is a test file.',
    size: 512,
  }

  const mockJsonDoc = {
    id: 'doc-3',
    name: 'config.json',
    type: 'json' as const,
    content: JSON.stringify({ key: 'value', nested: { foo: 'bar' } }),
    size: 256,
  }

  const mockPdfDoc = {
    id: 'doc-4',
    name: 'report.pdf',
    type: 'pdf' as const,
    content: 'data:application/pdf;base64,fakepdf',
    size: 4096,
  }

  const defaultProps = {
    onClose: vi.fn(),
    onNavigate: vi.fn(),
    hasNext: false,
    hasPrev: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders image viewer for image documents', () => {
    render(
      <DocumentViewer document={mockImageDoc} {...defaultProps} />
    )

    expect(screen.getByTestId('document-viewer')).toBeInTheDocument()
    expect(screen.getByTestId('image-viewer')).toBeInTheDocument()
    expect(screen.getByAltText('photo.png')).toHaveAttribute('src', 'data:image/png;base64,fakeimage')
  })

  it('renders text viewer for text documents', () => {
    render(
      <DocumentViewer document={mockTextDoc} {...defaultProps} />
    )

    expect(screen.getByTestId('text-viewer')).toBeInTheDocument()
    expect(screen.getByText(/Hello world/)).toBeInTheDocument()
    expect(screen.getByText(/This is a test file/)).toBeInTheDocument()
  })

  it('renders JSON viewer with formatted output', () => {
    render(
      <DocumentViewer document={mockJsonDoc} {...defaultProps} />
    )

    expect(screen.getByTestId('json-viewer')).toBeInTheDocument()
    expect(screen.getByText(/"key": "value"/)).toBeInTheDocument()
  })

  it('renders PDF viewer via iframe', () => {
    render(
      <DocumentViewer document={mockPdfDoc} {...defaultProps} />
    )

    expect(screen.getByTestId('pdf-viewer')).toBeInTheDocument()
    expect(screen.getByTitle('PDF Viewer')).toHaveAttribute('src', 'data:application/pdf;base64,fakepdf')
  })

  it('shows document name and type in header', () => {
    render(
      <DocumentViewer document={mockImageDoc} {...defaultProps} />
    )

    expect(screen.getByText('photo.png')).toBeInTheDocument()
    expect(screen.getByText('IMAGE')).toBeInTheDocument()
  })

  it('calls onClose when close button is clicked', () => {
    render(
      <DocumentViewer document={mockImageDoc} {...defaultProps} />
    )

    fireEvent.click(screen.getByTestId('close-button'))
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when overlay is clicked', () => {
    render(
      <DocumentViewer document={mockImageDoc} {...defaultProps} />
    )

    fireEvent.click(screen.getByTestId('document-viewer-overlay'))
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onNavigate when next/prev buttons are clicked', () => {
    render(
      <DocumentViewer document={mockImageDoc} {...defaultProps} hasNext={true} hasPrev={true} />
    )

    fireEvent.click(screen.getByTestId('next-button'))
    expect(defaultProps.onNavigate).toHaveBeenCalledWith('next')

    fireEvent.click(screen.getByTestId('prev-button'))
    expect(defaultProps.onNavigate).toHaveBeenCalledWith('prev')
  })

  it('does not show next/prev buttons when not available', () => {
    render(
      <DocumentViewer document={mockImageDoc} {...defaultProps} hasNext={false} hasPrev={false} />
    )

    expect(screen.queryByTestId('next-button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('prev-button')).not.toBeInTheDocument()
  })

  it('has download button', () => {
    render(
      <DocumentViewer document={mockImageDoc} {...defaultProps} />
    )

    expect(screen.getByTestId('download-button')).toBeInTheDocument()
  })

  it('handles keyboard navigation', () => {
    render(
      <DocumentViewer document={mockImageDoc} {...defaultProps} hasNext={true} hasPrev={true} />
    )

    fireEvent.keyDown(window, { key: 'Escape' })
    expect(defaultProps.onClose).toHaveBeenCalledTimes(1)

    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(defaultProps.onNavigate).toHaveBeenCalledWith('next')

    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(defaultProps.onNavigate).toHaveBeenCalledWith('prev')
  })
})

describe('useDocuments', () => {
  it('starts with no documents', () => {
    const { result } = renderHook(() => useDocuments())

    expect(result.current.documents).toEqual([])
    expect(result.current.activeDocument).toBeNull()
  })

  it('opens a document', () => {
    const { result } = renderHook(() => useDocuments())

    act(() => {
      result.current.openDocument({
        name: 'test.png',
        type: 'image/png',
        size: 1024,
        content: 'data:image/png;base64,abc',
      })
    })

    expect(result.current.documents).toHaveLength(1)
    expect(result.current.activeDocument?.name).toBe('test.png')
    expect(result.current.activeDocument?.type).toBe('image')
  })

  it('closes a document by id', () => {
    const { result } = renderHook(() => useDocuments())

    act(() => {
      result.current.openDocument({
        name: 'test.png',
        type: 'image/png',
        size: 1024,
        content: 'data:image/png;base64,abc',
      })
    })

    const docId = result.current.documents[0].id

    act(() => {
      result.current.closeDocument(docId)
    })

    expect(result.current.documents).toHaveLength(0)
    expect(result.current.activeDocument).toBeNull()
  })

  it('navigates between documents', () => {
    const { result } = renderHook(() => useDocuments())

    act(() => {
      result.current.openDocument({ name: 'first.txt', type: 'text/plain', size: 100, content: 'first' })
      result.current.openDocument({ name: 'second.txt', type: 'text/plain', size: 200, content: 'second' })
      result.current.openDocument({ name: 'third.txt', type: 'text/plain', size: 300, content: 'third' })
    })

    expect(result.current.activeDocument?.name).toBe('third.txt')

    act(() => {
      result.current.navigateDocument('prev')
    })
    expect(result.current.activeDocument?.name).toBe('second.txt')

    act(() => {
      result.current.navigateDocument('prev')
    })
    expect(result.current.activeDocument?.name).toBe('first.txt')

    act(() => {
      result.current.navigateDocument('next')
    })
    expect(result.current.activeDocument?.name).toBe('second.txt')
  })

  it('detects document types correctly', () => {
    const { result } = renderHook(() => useDocuments())

    act(() => {
      result.current.openDocument({ name: 'photo.png', type: 'image/png', size: 100, content: 'data:image/png;base64,x' })
      result.current.openDocument({ name: 'notes.txt', type: 'text/plain', size: 100, content: 'hello' })
      result.current.openDocument({ name: 'data.json', type: 'application/json', size: 100, content: '{}' })
      result.current.openDocument({ name: 'report.pdf', type: 'application/pdf', size: 100, content: 'data:application/pdf;base64,x' })
    })

    const types = result.current.documents.map((d) => d.type)
    expect(types).toEqual(['image', 'text', 'json', 'pdf'])
  })

  it('does not duplicate documents with same name and content', () => {
    const { result } = renderHook(() => useDocuments())

    const doc = { name: 'test.png', type: 'image/png', size: 1024, content: 'data:image/png;base64,abc' }

    act(() => {
      result.current.openDocument(doc)
      result.current.openDocument(doc)
    })

    expect(result.current.documents).toHaveLength(1)
  })
})
