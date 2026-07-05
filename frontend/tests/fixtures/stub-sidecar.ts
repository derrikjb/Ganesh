/**
 * Minimal stub of the Ganesh FastAPI sidecar.
 *
 * Implements the same HTTP contract as `backend/main.py` (the real sidecar)
 * but as a pure-Node HTTP server so integration tests have no Python
 * dependency. Mirrors:
 *   - GET  /health    → {"status":"ok"}
 *   - POST /shutdown  → {"status":"shutting down"} (stops the server)
 *   - CORS for tauri://localhost, https://tauri.localhost, http://localhost:5173
 *   - Prints `PORT: <port>` to stdout once bound (same protocol as the real sidecar)
 *
 * Used by Playwright integration tests via `helpers.ts`.
 */
import { createServer, type Server } from 'node:http'

export interface StubSidecar {
  server: Server
  port: number
  /** Resolves once the server has stopped accepting connections. */
  closed: Promise<void>
  /** Stop the server gracefully. */
  kill(): Promise<void>
  /** Increment to simulate sidecar restarts (for observability in tests). */
  restartCount: number
}

const CORS_ORIGINS = [
  'tauri://localhost',
  'https://tauri.localhost',
  'http://localhost:5173',
]

export function createStubSidecar(port = 18008): Promise<StubSidecar> {
  const server = createServer((req, res) => {
    const origin = req.headers.origin
    if (origin && CORS_ORIGINS.includes(origin)) {
      res.setHeader('Access-Control-Allow-Origin', origin)
      res.setHeader('Vary', 'Origin')
      res.setHeader('Access-Control-Allow-Credentials', 'true')
      res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS,*')
      res.setHeader('Access-Control-Allow-Headers', '*')
    }

    if (req.method === 'OPTIONS') {
      res.writeHead(204)
      res.end()
      return
    }

    const url = req.url ?? '/'

    if (url === '/health' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ status: 'ok' }))
      return
    }

    if (url === '/shutdown' && req.method === 'POST') {
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ status: 'shutting down' }))
      setImmediate(() => server.close())
      return
    }

    res.writeHead(404, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ detail: 'Not Found' }))
  })

  let closedResolve: () => void
  const closed = new Promise<void>((resolve) => {
    closedResolve = resolve
  })
  server.on('close', () => closedResolve())

  const stub: StubSidecar = {
    server,
    port,
    closed,
    restartCount: 0,
    async kill(): Promise<void> {
      await new Promise<void>((resolve) => {
        server.close(() => resolve())
      })
    },
  }

  return new Promise<StubSidecar>((resolve, reject) => {
    server.on('error', reject)
    server.listen(port, '127.0.0.1', () => {
      process.stdout.write(`PORT: ${port}\n`)
      resolve(stub)
    })
  })
}

// Allow direct CLI execution: `node --loader tsx stub-sidecar.ts`
if (import.meta.url === `file://${process.argv[1]}`) {
  const port = Number(process.env.STUB_SIDECAR_PORT ?? 18008)
  createStubSidecar(port).catch((err) => {
    console.error('stub-sidecar failed:', err)
    process.exit(1)
  })
}
