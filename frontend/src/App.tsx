import { useState } from 'react'
import { useSidecar } from './useSidecar'
import { ThemeProvider, useTheme } from './contexts/ThemeContext'
import { AccessibilityProvider } from './contexts/AccessibilityContext'
import { ChatContainer } from './components/ChatContainer'
import { ThemeSwitcher } from './components/ThemeSwitcher'
import { AccessibilitySettings } from './components/AccessibilitySettings'

function AppContent() {
  const { sidecarUrl, isReady, attempts } = useSidecar()
  const { theme } = useTheme()
  const [showThemePanel, setShowThemePanel] = useState(false)
  const [showA11yPanel, setShowA11yPanel] = useState(false)

  const statusText = isReady
    ? `Connected${sidecarUrl ? ` · ${sidecarUrl}` : ''}`
    : `Connecting… (attempt ${attempts})`

  const statusColor = isReady ? 'text-status-success' : 'text-status-warning'

  return (
    <div className="min-h-screen flex flex-col bg-bg-primary text-text-primary">
      <header className="flex items-center justify-between px-6 py-4 border-b border-border">
        <h1 className="text-2xl font-semibold tracking-tight">Ganesh</h1>
        <div className="flex items-center gap-4">
          <span className={`text-sm ${statusColor}`}>{statusText}</span>
          <button
            onClick={() => setShowA11yPanel((v) => !v)}
            className="p-2 rounded-md hover:bg-bg-secondary transition-colors text-text-muted hover:text-text-primary"
            data-testid="a11y-toggle-button"
            aria-label="Toggle accessibility settings"
            aria-expanded={showA11yPanel}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <circle cx="12" cy="4" r="2" />
              <path d="M19 7c-3 2-7 2-10 0" />
              <path d="M12 6v6" />
              <path d="M9 22l3-10 3 10" />
            </svg>
          </button>
          <button
            onClick={() => setShowThemePanel(!showThemePanel)}
            className="p-2 rounded-md hover:bg-bg-secondary transition-colors text-text-muted hover:text-text-primary"
            data-testid="theme-toggle-button"
            aria-label="Toggle theme panel"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="5" />
              <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
            </svg>
          </button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <main className="flex-1 flex flex-col overflow-hidden">
          <ChatContainer documents={[]} onOpenDocument={() => {}} />
        </main>

        {showThemePanel && (
          <aside className="w-72 border-l border-border bg-bg-secondary p-4 overflow-y-auto">
            <ThemeSwitcher />
          </aside>
        )}

        {showA11yPanel && (
          <aside className="w-72 border-l border-border bg-bg-secondary p-4 overflow-y-auto">
            <AccessibilitySettings onClose={() => setShowA11yPanel(false)} />
          </aside>
        )}
      </div>

      <footer className="px-6 py-3 border-t border-border text-xs text-text-muted">
        Ganesh AI Assistant · v0.1.0 · {theme}
      </footer>
    </div>
  )
}

function App() {
  return (
    <ThemeProvider>
      <AccessibilityProvider>
        <AppContent />
      </AccessibilityProvider>
    </ThemeProvider>
  )
}

export default App
