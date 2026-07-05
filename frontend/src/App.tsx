import { useSidecar } from './useSidecar'
import { ThemeProvider } from './contexts/ThemeContext'

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

      <main className="flex-1 flex items-center justify-center px-6 py-8">
        {isReady ? (
          <p className="text-text-secondary">Sidecar ready.</p>
        ) : (
          <div className="flex flex-col items-center gap-3 text-text-muted">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-border-subtle border-t-text-primary" />
            <p className="text-sm">Waiting for sidecar…</p>
          </div>
        )}
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
