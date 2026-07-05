import { test, expect } from '@playwright/test'
import { startStubSidecar, tauriInvokeShimScript, SIDECAR_PORT } from '../helpers'
import type { StubSidecar } from '../helpers'

test.describe('app launch', () => {
  let sidecar: StubSidecar

  test.beforeAll(async () => {
    sidecar = await startStubSidecar(SIDECAR_PORT)
  })

  test.afterAll(async () => {
    await sidecar.kill()
  })

  test('dev server starts and renders the Ganesh shell', async ({ page }) => {
    await page.addInitScript(tauriInvokeShimScript(SIDECAR_PORT))
    await page.goto('/')

    await expect(page.locator('h1')).toHaveText('Ganesh')
    await expect(page.getByText(/v0\.1\.0/)).toBeVisible()
  })

  test('sidecar /health responds ok', async () => {
    const res = await fetch(`http://127.0.0.1:${SIDECAR_PORT}/health`)
    expect(res.ok).toBe(true)
    const body = await res.json()
    expect(body.status).toBe('ok')
  })

  test('frontend reaches connected state and shows sidecar URL', async ({ page }) => {
    await page.addInitScript(tauriInvokeShimScript(SIDECAR_PORT))
    await page.goto('/')

    await expect(page.getByText(/Connected/)).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText(`127.0.0.1:${SIDECAR_PORT}`)).toBeVisible()
    await expect(page.getByText('Sidecar ready.')).toBeVisible()
  })
})
