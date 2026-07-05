import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright config for Ganesh integration tests.
 *
 * Strategy (fallback, CI-preferred): test the Vite dev server in a real
 * Chromium browser with a stub sidecar on port 18008. No Tauri binary
 * required. The stub sidecar is started per-test-suite via helpers.ts
 * (not via webServer) so individual tests can kill/restart it.
 *
 * Tauri WebDriver is not configured because tauri-driver is not available
 * in this environment; the Vite+stub approach is the primary path.
 */
export default defineConfig({
  testDir: './tests/integration',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    headless: true,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
})
