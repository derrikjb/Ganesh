import { test, expect } from '@playwright/test'
import {
  startStubSidecar,
  tauriInvokeShimScript,
  SIDECAR_PORT,
  waitForSidecar,
} from '../helpers'
import type { StubSidecar } from '../helpers'

test.describe('sidecar restart', () => {
  let sidecar: StubSidecar

  test.beforeAll(async () => {
    sidecar = await startStubSidecar(SIDECAR_PORT)
  })

  test.afterAll(async () => {
    try {
      await sidecar.kill()
    } catch {
    }
  })

  test('frontend shows reconnecting state after sidecar dies', async ({ page }) => {
    await page.addInitScript(tauriInvokeShimScript(SIDECAR_PORT))
    await page.goto('/')

    await expect(page.getByText(/Connected/)).toBeVisible({ timeout: 10_000 })

    await sidecar.kill()

    await expect(page.getByText(/Connecting/)).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText(/Welcome to Ganesh/)).toBeVisible()
  })

  test('frontend reconnects when sidecar comes back', async ({ page }) => {
    await page.addInitScript(tauriInvokeShimScript(SIDECAR_PORT))
    await page.goto('/')

    await expect(page.getByText(/Connecting/)).toBeVisible({ timeout: 10_000 })

    sidecar = await startStubSidecar(SIDECAR_PORT)
    await waitForSidecar(SIDECAR_PORT)

    await expect(page.getByText(/Connected/)).toBeVisible({ timeout: 15_000 })
  })
})
