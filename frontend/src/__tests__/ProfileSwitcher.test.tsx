import '@testing-library/jest-dom'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { ProfileSwitcher, type Profile, type BridgeGrant, type AuditEntry } from '../components/ProfileSwitcher'

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('../api', () => ({
  sidecarFetch: vi.fn(),
  getSidecarPort: vi.fn(),
}))

import { sidecarFetch } from '../api'

const mockFetch = sidecarFetch as ReturnType<typeof vi.fn>

function mockResponse(body: unknown, init: { ok?: boolean; status?: number } = {}): Response {
  return {
    ok: init.ok ?? true,
    status: init.status ?? 200,
    json: async () => body,
  } as unknown as Response
}

const PROFILES: Profile[] = [
  {
    id: 'profile-a',
    name: 'Work',
    description: 'Work profile',
    color: '#ff0000',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'profile-b',
    name: 'Personal',
    description: null,
    color: '#00ff00',
    created_at: '2026-01-02T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  },
]

const GRANTS: BridgeGrant[] = [
  {
    id: 'grant-1',
    granting_profile_id: 'profile-a',
    receiving_profile_id: 'profile-b',
    memory_id: 'memory-xyz',
    created_at: '2026-01-03T00:00:00Z',
  },
]

const AUDIT: AuditEntry[] = [
  {
    id: 1,
    receiving_profile_id: 'profile-b',
    granting_profile_id: 'profile-a',
    query: 'meeting',
    timestamp: '2026-01-03T00:00:00Z',
  },
]

function setupInitialMocks(): void {
  mockFetch.mockReset()
  // Initial load: profiles, grants, audit (in that order).
  mockFetch.mockResolvedValueOnce(
    mockResponse({ profiles: PROFILES, active_profile_id: 'profile-a' }),
  )
  mockFetch.mockResolvedValueOnce(mockResponse({ grants: GRANTS }))
  mockFetch.mockResolvedValueOnce(mockResponse({ entries: AUDIT }))
}

describe('ProfileSwitcher', () => {
  beforeEach(() => {
    setupInitialMocks()
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('renders profiles with active badge on the active profile', async () => {
    render(<ProfileSwitcher refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('profile-row-profile-a')).toBeInTheDocument()
    })

    expect(screen.getByTestId('profile-row-profile-b')).toBeInTheDocument()
    expect(screen.getByTestId('profile-active-badge-profile-a')).toBeInTheDocument()
    expect(screen.queryByTestId('profile-active-badge-profile-b')).toBeNull()
    expect(screen.getByTestId('active-profile-indicator').textContent).toContain('Work')
  })

  it('creates a profile via POST /api/profiles', async () => {
    render(<ProfileSwitcher refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('profile-create-btn')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByTestId('profile-new-name'), { target: { value: 'Side Project' } })
    fireEvent.change(screen.getByTestId('profile-new-desc'), { target: { value: 'Weekend work' } })

    // POST create → 201; then refresh fetches the updated list.
    mockFetch.mockResolvedValueOnce(mockResponse({ id: 'profile-c', name: 'Side Project' }))
    mockFetch.mockResolvedValueOnce(
      mockResponse({
        profiles: [...PROFILES, {
          id: 'profile-c',
          name: 'Side Project',
          description: 'Weekend work',
          color: '#7c3aed',
          created_at: '2026-01-04T00:00:00Z',
          updated_at: '2026-01-04T00:00:00Z',
        }],
        active_profile_id: 'profile-a',
      }),
    )

    fireEvent.click(screen.getByTestId('profile-create-btn'))

    await waitFor(() => {
      const createCall = mockFetch.mock.calls.find(
        ([path, init]) =>
          path === '/api/profiles' && (init as RequestInit)?.method === 'POST',
      )
      expect(createCall).toBeDefined()
    })
  })

  it('activates a profile via POST /api/profiles/{id}/activate', async () => {
    render(<ProfileSwitcher refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('profile-activate-profile-b')).toBeInTheDocument()
    })

    mockFetch.mockResolvedValueOnce(mockResponse(PROFILES[1]))
    mockFetch.mockResolvedValueOnce(
      mockResponse({ profiles: PROFILES, active_profile_id: 'profile-b' }),
    )

    fireEvent.click(screen.getByTestId('profile-activate-profile-b'))

    await waitFor(() => {
      const activateCall = mockFetch.mock.calls.find(
        ([path, init]) =>
          path === '/api/profiles/profile-b/activate' && (init as RequestInit)?.method === 'POST',
      )
      expect(activateCall).toBeDefined()
    })
  })

  it('deletes a profile via DELETE /api/profiles/{id}', async () => {
    render(<ProfileSwitcher refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('profile-delete-profile-b')).toBeInTheDocument()
    })

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)

    mockFetch.mockResolvedValueOnce(mockResponse(null, { status: 204 }))
    mockFetch.mockResolvedValueOnce(
      mockResponse({ profiles: [PROFILES[0]], active_profile_id: 'profile-a' }),
    )
    mockFetch.mockResolvedValueOnce(mockResponse({ grants: [] }))

    fireEvent.click(screen.getByTestId('profile-delete-profile-b'))

    await waitFor(() => {
      const deleteCall = mockFetch.mock.calls.find(
        ([path, init]) =>
          path === '/api/profiles/profile-b' && (init as RequestInit)?.method === 'DELETE',
      )
      expect(deleteCall).toBeDefined()
    })

    confirmSpy.mockRestore()
  })

  it('creates a bridge grant via POST /api/profiles/bridge/grant', async () => {
    render(<ProfileSwitcher refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('grant-create-btn')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByTestId('grant-granting'), { target: { value: 'profile-a' } })
    fireEvent.change(screen.getByTestId('grant-receiving'), { target: { value: 'profile-b' } })
    fireEvent.change(screen.getByTestId('grant-memory-id'), { target: { value: 'memory-123' } })

    mockFetch.mockResolvedValueOnce(
      mockResponse({
        id: 'grant-2',
        granting_profile_id: 'profile-a',
        receiving_profile_id: 'profile-b',
        memory_id: 'memory-123',
        created_at: '2026-01-05T00:00:00Z',
      }),
    )
    mockFetch.mockResolvedValueOnce(mockResponse({ grants: [...GRANTS, {
      id: 'grant-2',
      granting_profile_id: 'profile-a',
      receiving_profile_id: 'profile-b',
      memory_id: 'memory-123',
      created_at: '2026-01-05T00:00:00Z',
    }] }))

    fireEvent.click(screen.getByTestId('grant-create-btn'))

    await waitFor(() => {
      const grantCall = mockFetch.mock.calls.find(
        ([path, init]) =>
          path === '/api/profiles/bridge/grant' && (init as RequestInit)?.method === 'POST',
      )
      expect(grantCall).toBeDefined()
      const body = JSON.parse((grantCall![1] as RequestInit).body as string)
      expect(body.granting_profile_id).toBe('profile-a')
      expect(body.receiving_profile_id).toBe('profile-b')
      expect(body.memory_id).toBe('memory-123')
    })
  })

  it('revokes a grant via DELETE /api/profiles/bridge/grant/{id}', async () => {
    render(<ProfileSwitcher refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('grant-revoke-grant-1')).toBeInTheDocument()
    })

    mockFetch.mockResolvedValueOnce(mockResponse(null, { status: 204 }))
    mockFetch.mockResolvedValueOnce(mockResponse({ grants: [] }))

    fireEvent.click(screen.getByTestId('grant-revoke-grant-1'))

    await waitFor(() => {
      const revokeCall = mockFetch.mock.calls.find(
        ([path, init]) =>
          path === '/api/profiles/bridge/grant/grant-1' && (init as RequestInit)?.method === 'DELETE',
      )
      expect(revokeCall).toBeDefined()
    })
  })

  it('runs a bridge query and displays results', async () => {
    render(<ProfileSwitcher refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('query-run-btn')).toBeInTheDocument()
    })

    fireEvent.change(screen.getByTestId('query-granting'), { target: { value: 'profile-a' } })
    fireEvent.change(screen.getByTestId('query-text'), { target: { value: 'meeting schedule' } })

    mockFetch.mockResolvedValueOnce(
      mockResponse({
        query: 'meeting schedule',
        receiving_profile_id: 'profile-a',
        granting_profile_id: 'profile-a',
        results: [
          {
            id: 'memory-xyz',
            content: 'Team meeting on Friday at 2pm',
            metadata: {},
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
          },
        ],
      }),
    )
    mockFetch.mockResolvedValueOnce(mockResponse({ entries: AUDIT }))

    fireEvent.click(screen.getByTestId('query-run-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('query-results')).toBeInTheDocument()
    })
    expect(screen.getByTestId('query-result-memory-xyz').textContent).toContain('Friday')
  })

  it('shows error message when fetch fails', async () => {
    mockFetch.mockReset()
    mockFetch.mockRejectedValueOnce(new Error('network down'))
    mockFetch.mockResolvedValueOnce(mockResponse({ grants: [] }))
    mockFetch.mockResolvedValueOnce(mockResponse({ entries: [] }))

    render(<ProfileSwitcher refreshIntervalMs={99999} />)

    await waitFor(() => {
      expect(screen.getByTestId('profile-error')).toBeInTheDocument()
    })
    expect(screen.getByTestId('profile-error').textContent).toContain('network down')
  })
})
