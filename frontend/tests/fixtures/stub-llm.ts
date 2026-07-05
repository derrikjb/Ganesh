/**
 * Mock LLM endpoint returning canned responses.
 *
 * Exposes a minimal OpenAI-compatible `/v1/chat/completions` endpoint so
 * future feature tests can exercise chat UI without real API calls or keys.
 * Responses are deterministic and instant.
 */
import { createServer, type Server } from 'node:http'

export interface StubLLM {
  server: Server
  port: number
  closed: Promise<void>
  kill(): Promise<void>
  /** Number of chat-completion requests received. */
  requestCount: number
}

const CANNED_RESPONSE = 'Ganesh stub LLM response: hello from the test fixture.'

export function createStubLLM(port = 18009): Promise<StubLLM> {
  let requestCount = 0
  const server = createServer((req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*')
    res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS,*')
    res.setHeader('Access-Control-Allow-Headers', '*')

    if (req.method === 'OPTIONS') {
      res.writeHead(204)
      res.end()
      return
    }

    const url = req.url ?? '/'
    if (url === '/v1/chat/completions' && req.method === 'POST') {
      requestCount++
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(
        JSON.stringify({
          id: 'chatcmpl-stub',
          object: 'chat.completion',
          choices: [
            { index: 0, message: { role: 'assistant', content: CANNED_RESPONSE }, finish_reason: 'stop' },
          ],
          usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
        }),
      )
      return
    }

    if (url === '/health' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ status: 'ok' }))
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

  const stub: StubLLM = {
    server,
    port,
    closed,
    requestCount,
    async kill(): Promise<void> {
      await new Promise<void>((resolve) => {
        server.close(() => resolve())
      })
    },
  }

  return new Promise<StubLLM>((resolve, reject) => {
    server.on('error', reject)
    server.listen(port, '127.0.0.1', () => resolve(stub))
  })
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const port = Number(process.env.STUB_LLM_PORT ?? 18009)
  createStubLLM(port).catch((err: unknown) => {
    console.error('stub-llm failed:', err)
    process.exit(1)
  })
}
