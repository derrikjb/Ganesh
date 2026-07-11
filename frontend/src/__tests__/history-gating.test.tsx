import '@testing-library/jest-dom'
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import App from '../App'

vi.mock('../useSidecar', () => ({
  useSidecar: () => ({
    sidecarUrl: 'http://localhost:1234',
    isReady: true,
    attempts: 0,
    status: 'ready',
    restartSidecar: vi.fn(),
  }),
}))

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('../api', () => ({
  sidecarFetch: vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({}) })),
  getSidecarPort: vi.fn(),
}))

vi.mock('@tauri-apps/api/event', () => ({
  listen: vi.fn(() => Promise.resolve(() => {})),
}))

describe('App History Gating', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
  })

  it('renders history toggle button when in DEV mode', () => {
    vi.stubEnv('DEV', true)
    render(<App />)
    expect(screen.getByTestId('history-toggle-button')).toBeInTheDocument()
  })

  it('does not render history toggle button when not in DEV mode', () => {
    vi.stubEnv('DEV', false)
    render(<App />)
    expect(screen.queryByTestId('history-toggle-button')).not.toBeInTheDocument()
  })
})
