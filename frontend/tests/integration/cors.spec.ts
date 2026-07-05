import { test, expect } from '@playwright/test'
import { startStubSidecar, tauriInvokeShimScript, SIDECAR_PORT } from '../helpers'
import type { StubSidecar } from '../helpers'

test.describe('CORS', () => {
  let sidecar: StubSidecar

  test.beforeAll(async () => {
    sidecar = await startStubSidecar(SIDECAR_PORT)
  })

  test.afterAll(async () => {
    await sidecar.kill()
  })

  test('browser can fetch /health from dev-server origin without CORS errors', async ({ page }) => {
    const corsErrors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error' && /CORS|Access-Control/i.test(msg.text())) {
        corsErrors.push(msg.text())
      }
    })
    page.on('pageerror', (err) => {
      if (/CORS|Access-Control|Failed to fetch/i.test(err.message)) {
        corsErrors.push(err.message)
      }
    })

    await page.addInitScript(tauriInvokeShimScript(SIDECAR_PORT))
    await page.goto('/')

    await expect(page.getByText(/Connected/)).toBeVisible({ timeout: 10_000 })

    const fetched = await page.evaluate(async (port) => {
      const res = await fetch(`http://127.0.0.1:${port}/health`)
      return { ok: res.ok, status: res.status, body: await res.json() }
    }, SIDECAR_PORT)

    expect(fetched.ok).toBe(true)
    expect(fetched.status).toBe(200)
    expect(fetched.body.status).toBe('ok')
    expect(corsErrors).toEqual([])
  })
})
