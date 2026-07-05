import { useSidecar } from './useSidecar'

function App() {
  const { sidecarUrl, isReady, attempts } = useSidecar()

  const statusText = isReady
    ? `Connected${sidecarUrl ? ` · ${sidecarUrl}` : ''}`
    : `Connecting… (attempt ${attempts})`

  const statusColor = isReady ? 'text-emerald-400' : 'text-amber-400'

  return (
    <div className="min-h-screen flex flex-col bg-slate-900 text-slate-100">
      <header className="flex items-center justify-between px-6 py-4 border-b border-slate-800">
        <h1 className="text-2xl font-semibold tracking-tight">Ganesh</h1>
        <span className={`text-sm ${statusColor}`}>{statusText}</span>
      </header>

      <main className="flex-1 flex items-center justify-center px-6 py-8">
        {isReady ? (
          <p className="text-slate-300">Sidecar ready.</p>
        ) : (
          <div className="flex flex-col items-center gap-3 text-slate-400">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-600 border-t-slate-300" />
            <p className="text-sm">Waiting for sidecar…</p>
          </div>
        )}
      </main>

      <footer className="px-6 py-3 border-t border-slate-800 text-xs text-slate-500">
        Ganesh AI Assistant · v0.1.0
      </footer>
    </div>
  )
}

export default App
