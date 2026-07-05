import { useSidecar } from './useSidecar'
import { ThemeProvider } from './contexts/ThemeContext'
import { ChatContainer } from './components/ChatContainer'

function AppContent() {
  const { sidecarUrl, isReady, attempts } = useSidecar()

  const statusText = isReady
    ? `Connected${sidecarUrl ? ` · ${sidecarUrl}` : ''}`
    : `Connecting… (attempt ${attempts})`

  const statusColor = isReady ? 'text-status-success' : 'text-status-warning'

  return (
    <div className="min-h-screen flex flex-col bg-bg-primary text-text-primary">
      <header className="flex items-center justify-between px-6 py-4 border-b border-border">
        <h1 className="text-2xl font-semibold tracking-tight">Ganesh</h1>
        <span className={`text-sm ${statusColor}`}>{statusText}</span>
      </header>

      <main className="flex-1 flex flex-col overflow-hidden">
        <ChatContainer />
      </main>

      <footer className="px-6 py-3 border-t border-border text-xs text-text-muted">
        Ganesh AI Assistant · v0.1.0
      </footer>
    </div>
  )
}

function App() {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  )
}

export default App
