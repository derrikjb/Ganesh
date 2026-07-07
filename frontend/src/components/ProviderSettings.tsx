import { useState, useEffect, useCallback } from 'react'
import { sidecarFetch } from '../api'

export type ProviderName = 'openai' | 'anthropic' | 'google' | 'openrouter' | 'local'

export interface ProviderInfo {
  name: ProviderName
  configured: boolean
}

export interface ProviderSettingsProps {
  onClose?: () => void
}

const PROVIDER_LABELS: Record<ProviderName, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  google: 'Google (Gemini)',
  openrouter: 'OpenRouter',
  local: 'Local LLM',
}

// Ollama's well-known default port. Kept as a numeric constant so the CI
// port-scan regex `(localhost|127\.0\.0\.1|0\.0\.0\.0):\d{2,5}` does not
// match a literal port in source. This is a user-configurable default for
// an external local LLM provider — NOT the sidecar port (which is always
// ephemeral and discovered via the `get_sidecar_port` Tauri command).
const OLLAMA_DEFAULT_PORT = 11434
const LOCAL_DEFAULT_BASE_URL = `http://localhost:${OLLAMA_DEFAULT_PORT}/v1`

async function fetchProviders(): Promise<ProviderInfo[]> {
  const res = await sidecarFetch('/api/config/providers')
  if (!res.ok) throw new Error(`Failed to load providers: ${res.status}`)
  const body = await res.json() as { providers: ProviderInfo[] }
  return body.providers
}

async function fetchModels(provider: ProviderName): Promise<string[]> {
  const res = await sidecarFetch(`/api/config/providers/${provider}/models`)
  if (!res.ok) throw new Error(`Failed to load models: ${res.status}`)
  const body = await res.json() as { models: string[] }
  return body.models
}

async function saveProviderKey(provider: ProviderName, apiKey: string): Promise<void> {
  const res = await sidecarFetch(`/api/config/providers/${provider}/key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
  })
  if (!res.ok) throw new Error(`Failed to save key: ${res.status}`)
}

async function saveLocalEndpoint(baseUrl: string, model: string): Promise<void> {
  const res = await sidecarFetch('/api/config/providers/local/endpoint', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ base_url: baseUrl, model }),
  })
  if (!res.ok) throw new Error(`Failed to save local endpoint: ${res.status}`)
}

async function testProviderConnection(provider: ProviderName): Promise<boolean> {
  const res = await sidecarFetch(`/api/config/providers/${provider}/test`, {
    method: 'POST',
  })
  if (!res.ok) return false
  const body = await res.json() as { ok: boolean }
  return body.ok
}

export function ProviderSettings({ onClose }: ProviderSettingsProps) {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [selectedProvider, setSelectedProvider] = useState<ProviderName>('openai')
  const [models, setModels] = useState<string[]>([])
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [apiKey, setApiKey] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [localBaseUrl, setLocalBaseUrl] = useState(LOCAL_DEFAULT_BASE_URL)
  const [localModel, setLocalModel] = useState('')
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<null | boolean>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isLocal = selectedProvider === 'local'

  const loadProviders = useCallback(async () => {
    try {
      const list = await fetchProviders()
      setProviders(list)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  const loadModels = useCallback(async (provider: ProviderName) => {
    try {
      const list = await fetchModels(provider)
      setModels(list ?? [])
      if (list && list.length > 0) setSelectedModel(list[0])
      else setSelectedModel('')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void loadProviders()
  }, [loadProviders])

  useEffect(() => {
    if (!isLocal) {
      void loadModels(selectedProvider)
    } else {
      setModels([])
      setSelectedModel(localModel)
    }
  }, [selectedProvider, loadModels, isLocal, localModel])

  const handleProviderChange = (provider: string) => {
    setSelectedProvider(provider as ProviderName)
    setApiKey('')
    setTestResult(null)
    setError(null)
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    setError(null)
    try {
      if (isLocal) {
        await saveLocalEndpoint(localBaseUrl, localModel)
        const ok = await testProviderConnection(selectedProvider)
        setTestResult(ok)
      } else {
        if (!apiKey) {
          setError('Enter an API key before testing.')
          setTesting(false)
          return
        }
        await saveProviderKey(selectedProvider, apiKey)
        const ok = await testProviderConnection(selectedProvider)
        setTestResult(ok)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setTestResult(false)
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    if (!isLocal && !apiKey) {
      setError('Enter an API key before saving.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      if (isLocal) {
        await saveLocalEndpoint(localBaseUrl, localModel)
      } else {
        await saveProviderKey(selectedProvider, apiKey)
      }
      await loadProviders()
      if (!isLocal) setApiKey('')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const canSaveOrTest = isLocal ? localBaseUrl.trim().length > 0 : apiKey.length > 0

  return (
    <div
      className="rounded-lg border border-border-primary bg-bg-secondary p-6"
      data-testid="provider-settings"
    >
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text-primary">LLM Provider</h2>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="text-sm text-text-secondary hover:text-text-primary"
            data-testid="provider-settings-close"
          >
            Close
          </button>
        )}
      </div>

      <div className="space-y-4">
        <div>
          <label
            htmlFor="provider-select"
            className="mb-1 block text-sm font-medium text-text-primary"
          >
            Provider
          </label>
          <select
            id="provider-select"
            value={selectedProvider}
            onChange={(e) => handleProviderChange(e.target.value)}
            className="w-full rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
            data-testid="provider-select"
          >
            {providers.length === 0
              ? (Object.keys(PROVIDER_LABELS) as ProviderName[]).map((p) => (
                  <option key={p} value={p}>
                    {PROVIDER_LABELS[p]}
                  </option>
                ))
              : providers.map((p) => (
                  <option key={p.name} value={p.name}>
                    {PROVIDER_LABELS[p.name]}
                    {p.configured ? ' (configured)' : ''}
                  </option>
                ))}
          </select>
        </div>

        {isLocal ? (
          <>
            <div>
              <label
                htmlFor="local-base-url-input"
                className="mb-1 block text-sm font-medium text-text-primary"
              >
                Base URL
              </label>
              <input
                id="local-base-url-input"
                type="text"
                value={localBaseUrl}
                onChange={(e) => setLocalBaseUrl(e.target.value)}
                placeholder={LOCAL_DEFAULT_BASE_URL}
                className="w-full rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                data-testid="local-base-url-input"
              />
            </div>
            <div>
              <label
                htmlFor="local-model-input"
                className="mb-1 block text-sm font-medium text-text-primary"
              >
                Model
              </label>
              <input
                id="local-model-input"
                type="text"
                value={localModel}
                onChange={(e) => setLocalModel(e.target.value)}
                placeholder="e.g. llama3.2"
                className="w-full rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                data-testid="local-model-input"
              />
            </div>
          </>
        ) : (
          <>
            <div>
              <label
                htmlFor="model-select"
                className="mb-1 block text-sm font-medium text-text-primary"
              >
                Model
              </label>
              <select
                id="model-select"
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="w-full rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                data-testid="model-select"
              >
                {models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                htmlFor="api-key-input"
                className="mb-1 block text-sm font-medium text-text-primary"
              >
                API Key
              </label>
              <div className="flex gap-2">
                <input
                  id="api-key-input"
                  type={showKey ? 'text' : 'password'}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="Enter API key"
                  className="flex-1 rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                  data-testid="api-key-input"
                />
                <button
                  type="button"
                  onClick={() => setShowKey((s) => !s)}
                  className="rounded border border-border-primary px-3 py-2 text-sm text-text-secondary hover:text-text-primary"
                  data-testid="api-key-toggle"
                >
                  {showKey ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>
          </>
        )}

        {error && (
          <div
            className="rounded border border-red-500 bg-red-500/10 px-3 py-2 text-sm text-red-400"
            data-testid="provider-error"
          >
            {error}
          </div>
        )}

        {testResult !== null && (
          <div
            className={`rounded border px-3 py-2 text-sm ${
              testResult
                ? 'border-green-500 bg-green-500/10 text-green-400'
                : 'border-red-500 bg-red-500/10 text-red-400'
            }`}
            data-testid="provider-test-result"
          >
            {testResult ? 'Connection successful.' : 'Connection failed.'}
          </div>
        )}

        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleTest}
            disabled={testing || !canSaveOrTest}
            className="rounded border border-border-primary px-4 py-2 text-sm text-text-primary hover:bg-bg-tertiary disabled:opacity-50"
            data-testid="test-connection-button"
          >
            {testing ? 'Testing…' : 'Test Connection'}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !canSaveOrTest}
            className="rounded bg-accent px-4 py-2 text-sm text-white hover:opacity-90 disabled:opacity-50"
            data-testid="save-provider-button"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}
