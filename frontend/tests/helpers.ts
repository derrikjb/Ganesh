import { createStubSidecar, type StubSidecar } from './fixtures/stub-sidecar'
import { createStubLLM, type StubLLM } from './fixtures/stub-llm'

export const SIDECAR_PORT = 18008
export const LLM_PORT = 18009
export const DEV_SERVER_URL = 'http://localhost:5173'

export type { StubSidecar, StubLLM }

export async function waitForSidecar(
  port: number = SIDECAR_PORT,
  timeoutMs = 5000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/health`)
      if (res.ok) return
    } catch {
    }
    await new Promise((r) => setTimeout(r, 100))
  }
  throw new Error(`sidecar on port ${port} did not become healthy within ${timeoutMs}ms`)
}

export async function startStubSidecar(port: number = SIDECAR_PORT): Promise<StubSidecar> {
  const stub = await createStubSidecar(port)
  await waitForSidecar(port)
  return stub
}

export async function startStubLLM(port: number = LLM_PORT): Promise<StubLLM> {
  const stub = await createStubLLM(port)
  return stub
}

/**
 * Injects a fake `window.__TAURI_INTERNALS__.invoke` so the frontend's
 * `@tauri-apps/api/core` `invoke('get_sidecar_port')` returns the stub
 * sidecar port when running outside a real Tauri webview.
 *
 * Must run before any page script executes — use with `page.addInitScript`.
 */
export function tauriInvokeShimScript(port: number = SIDECAR_PORT): string {
  return `
    window.__TAURI_INTERNALS__ = window.__TAURI_INTERNALS__ || {};
    window.__TAURI_INTERNALS__.invoke = function(cmd, args, options) {
      if (cmd === 'get_sidecar_port') {
        return Promise.resolve(${port});
      }
      return Promise.reject(new Error('invoke not implemented in test shim: ' + cmd));
    };
    window.__TAURI_INTERNALS__.transformCallback = function(cb) { return 0; };
    window.__TAURI_INTERNALS__.unregisterCallback = function() {};
    Object.defineProperty(window, 'isTauri', { value: true, writable: false });
  `
}
