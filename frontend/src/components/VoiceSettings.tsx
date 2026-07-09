import { useState, useEffect, useCallback } from 'react'
import { open } from '@tauri-apps/plugin-dialog'
import { invoke } from '@tauri-apps/api/core'
import { sidecarFetch } from '../api'

interface PiperVoice {
  id: string
  name: string
  path: string
}

interface VoiceSettingsResponse {
  stt_engine: 'local' | 'cloud'
  tts_engine: 'local' | 'cloud'
  whisper_model: string
  stt_device: string
  tts_device: string
  deepgram_model: string
  elevenlabs_voice_id: string
  piper_voices: PiperVoice[]
  piper_active_voice: string | null
  stt_local_available: boolean
  stt_cloud_available: boolean
  tts_local_available: boolean
  tts_cloud_available: boolean
  cuda_available: boolean
  activation_mode: 'click_to_talk' | 'push_to_talk' | 'vad'
}

interface VoiceSettingsProps {
  onClose?: () => void
}

const WHISPER_MODELS = ['tiny', 'base', 'small', 'medium', 'large', 'large-v3', 'large-v3-turbo', 'distil-large-v3']
const STT_DEVICES = ['auto', 'cpu', 'cuda']
const TTS_DEVICES = ['auto', 'cpu', 'cuda']

async function fetchVoiceSettings(): Promise<VoiceSettingsResponse> {
  const res = await sidecarFetch('/api/voice/settings')
  if (!res.ok) throw new Error(`Failed to load voice settings: ${res.status}`)
  return (await res.json()) as VoiceSettingsResponse
}

async function saveVoiceSettings(updates: Partial<VoiceSettingsResponse>): Promise<VoiceSettingsResponse> {
  const res = await sidecarFetch('/api/voice/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  if (!res.ok) throw new Error(`Failed to save voice settings: ${res.status}`)
  return (await res.json()) as VoiceSettingsResponse
}

async function addPiperVoice(name: string, path: string): Promise<PiperVoice> {
  const res = await sidecarFetch('/api/voice/piper-voices', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, path }),
  })
  if (!res.ok) throw new Error(`Failed to add voice: ${res.status}`)
  return (await res.json()) as PiperVoice
}

async function removePiperVoice(id: string): Promise<void> {
  const res = await sidecarFetch(`/api/voice/piper-voices/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`Failed to remove voice: ${res.status}`)
}

async function activatePiperVoice(id: string): Promise<VoiceSettingsResponse> {
  const res = await sidecarFetch(`/api/voice/piper-voices/${id}/activate`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`Failed to activate voice: ${res.status}`)
  return (await res.json()) as VoiceSettingsResponse
}

async function saveApiKey(provider: string, apiKey: string): Promise<void> {
  const res = await sidecarFetch(`/api/voice/keys/${provider}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
  })
  if (!res.ok) throw new Error(`Failed to save API key: ${res.status}`)
}

export function VoiceSettings({ onClose }: VoiceSettingsProps) {
  const [settings, setSettings] = useState<VoiceSettingsResponse | null>(null)
  const [activationMode, setActivationMode] = useState<'click_to_talk' | 'push_to_talk' | 'vad'>('click_to_talk')
  const [pttHotkey, setPttHotkey] = useState('Control+Space')
  const [pttHotkeySaving, setPttHotkeySaving] = useState(false)
  const [sttEngine, setSttEngine] = useState<'local' | 'cloud'>('local')
  const [ttsEngine, setTtsEngine] = useState<'local' | 'cloud'>('local')
  const [whisperModel, setWhisperModel] = useState('tiny')
  const [sttDevice, setSttDevice] = useState('auto')
  const [ttsDevice, setTtsDevice] = useState('auto')
  const [deepgramModel, setDeepgramModel] = useState('nova-2')
  const [deepgramKey, setDeepgramKey] = useState('')
  const [elevenlabsKey, setElevenlabsKey] = useState('')
  const [elevenlabsVoiceId, setElevenlabsVoiceId] = useState('')
  const [showDeepgramKey, setShowDeepgramKey] = useState(false)
  const [showElevenlabsKey, setShowElevenlabsKey] = useState(false)
  const [newVoiceName, setNewVoiceName] = useState('')
  const [newVoicePath, setNewVoicePath] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const loadSettings = useCallback(async () => {
    try {
      const data = await fetchVoiceSettings()
      setSettings(data)
      setSttEngine(data.stt_engine)
      setTtsEngine(data.tts_engine)
      setWhisperModel(data.whisper_model)
      setSttDevice(data.stt_device)
      setTtsDevice(data.tts_device)
      setDeepgramModel(data.deepgram_model)
      setElevenlabsVoiceId(data.elevenlabs_voice_id)
      setActivationMode(data.activation_mode)
      setActivationMode(data.activation_mode)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void loadSettings()
    invoke<string>('get_ptt_hotkey').then(setPttHotkey).catch(() => {})
  }, [loadSettings])

  const handleSttEngineChange = async (engine: 'local' | 'cloud') => {
    setSttEngine(engine)
    setError(null)
    try {
      const updated = await saveVoiceSettings({ stt_engine: engine })
      setSettings(updated)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleTtsEngineChange = async (engine: 'local' | 'cloud') => {
    setTtsEngine(engine)
    setError(null)
    try {
      const updated = await saveVoiceSettings({ tts_engine: engine })
      setSettings(updated)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleWhisperModelChange = async (model: string) => {
    setWhisperModel(model)
    setError(null)
    try {
      const updated = await saveVoiceSettings({ whisper_model: model })
      setSettings(updated)
      setSuccess('Whisper model updated.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleDeepgramModelSave = async () => {
    setError(null)
    try {
      const updated = await saveVoiceSettings({ deepgram_model: deepgramModel })
      setSettings(updated)
      setSuccess('Deepgram model updated.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleDeepgramKeySave = async () => {
    if (!deepgramKey.trim()) {
      setError('Enter an API key before saving.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await saveApiKey('deepgram', deepgramKey)
      setDeepgramKey('')
      setSuccess('Deepgram API key saved.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const handleElevenlabsKeySave = async () => {
    if (!elevenlabsKey.trim()) {
      setError('Enter an API key before saving.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await saveApiKey('elevenlabs', elevenlabsKey)
      setElevenlabsKey('')
      setSuccess('ElevenLabs API key saved.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const handleElevenlabsVoiceIdSave = async () => {
    setError(null)
    try {
      const updated = await saveVoiceSettings({ elevenlabs_voice_id: elevenlabsVoiceId })
      setSettings(updated)
      setSuccess('ElevenLabs voice ID updated.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleAddVoice = async () => {
    if (!newVoiceName.trim() || !newVoicePath.trim()) {
      setError('Enter both a name and path for the voice.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      await addPiperVoice(newVoiceName, newVoicePath)
      setNewVoiceName('')
      setNewVoicePath('')
      await loadSettings()
      setSuccess('Voice added.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const handleRemoveVoice = async (id: string) => {
    setError(null)
    try {
      await removePiperVoice(id)
      await loadSettings()
      setSuccess('Voice removed.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleActivateVoice = async (id: string) => {
    setError(null)
    try {
      const updated = await activatePiperVoice(id)
      setSettings(updated)
      setSuccess('Voice activated.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleActivationModeChange = async (mode: 'click_to_talk' | 'push_to_talk' | 'vad') => {
    setActivationMode(mode)
    setError(null)
    try {
      const updated = await saveVoiceSettings({ activation_mode: mode })
      setSettings(updated)
      window.dispatchEvent(new CustomEvent('ganesh:activation-mode-changed', { detail: mode }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const piperVoices = settings?.piper_voices ?? []
  const activeVoiceId = settings?.piper_active_voice ?? null

  return (
    <div
      className="rounded-lg border border-border-primary bg-bg-secondary p-6"
      data-testid="voice-settings"
    >
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-text-primary">Voice Settings</h2>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="text-sm text-text-secondary hover:text-text-primary"
            data-testid="voice-settings-close"
          >
            Close
          </button>
        )}
      </div>

      <div className="space-y-6">
        {/* Activation Mode Section */}
        <div>
          <h3 className="mb-2 text-sm font-medium text-text-primary">Voice Input Mode</h3>
          <select
            value={activationMode}
            onChange={(e) => handleActivationModeChange(e.target.value as 'click_to_talk' | 'push_to_talk' | 'vad')}
            className="w-full rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
            data-testid="activation-mode-select"
          >
            <option value="click_to_talk">Click to Talk</option>
            <option value="push_to_talk">Push to Talk</option>
            <option value="vad">Voice Activity Detection</option>
          </select>
          <p className="mt-1 text-xs text-text-muted">
            {activationMode === 'click_to_talk' && 'Click the mic button to start/stop recording.'}
            {activationMode === 'push_to_talk' && 'Press the hotkey to start/stop recording. Works even when the window is hidden.'}
            {activationMode === 'vad' && 'Automatically starts recording when you speak.'}
          </p>
          {activationMode === 'push_to_talk' && (
            <div className="mt-2">
              <label htmlFor="ptt-hotkey-input" className="mb-1 block text-xs text-text-secondary">
                Push-to-Talk Hotkey
              </label>
              <div className="flex gap-2">
                <input
                  id="ptt-hotkey-input"
                  type="text"
                  value={pttHotkey}
                  onChange={(e) => setPttHotkey(e.target.value)}
                  placeholder="Control+Space"
                  className="flex-1 rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                  data-testid="ptt-hotkey-input"
                />
                <button
                  type="button"
                  onClick={async () => {
                    setPttHotkeySaving(true)
                    try {
                      const result = await invoke<string>('set_ptt_hotkey', { hotkey: pttHotkey })
                      setPttHotkey(result)
                    } catch {
                      setError('Failed to set hotkey. Use format like Control+Space or Alt+Shift+R.')
                    } finally {
                      setPttHotkeySaving(false)
                    }
                  }}
                  disabled={pttHotkeySaving}
                  className="rounded border border-border-primary px-3 py-2 text-sm text-text-secondary hover:text-text-primary"
                  data-testid="ptt-hotkey-save"
                >
                  {pttHotkeySaving ? 'Saving…' : 'Set'}
                </button>
              </div>
              <p className="mt-1 text-xs text-text-muted">
                Use modifier+key format (e.g. Control+Space, Alt+Shift+R, Super+M).
              </p>
            </div>
          )}
        </div>

        {/* STT Section */}
        <div>
          <h3 className="mb-2 text-sm font-medium text-text-primary">Speech-to-Text</h3>

          <div className="mb-3 flex gap-2">
            <button
              type="button"
              onClick={() => handleSttEngineChange('local')}
              className={`rounded border px-3 py-1.5 text-sm ${
                sttEngine === 'local'
                  ? 'border-accent bg-accent text-text-inverse'
                  : 'border-border-primary text-text-secondary hover:text-text-primary'
              }`}
              data-testid="stt-local-toggle"
            >
              Local
            </button>
            <button
              type="button"
              onClick={() => handleSttEngineChange('cloud')}
              className={`rounded border px-3 py-1.5 text-sm ${
                sttEngine === 'cloud'
                  ? 'border-accent bg-accent text-text-inverse'
                  : 'border-border-primary text-text-secondary hover:text-text-primary'
              }`}
              data-testid="stt-cloud-toggle"
            >
              Cloud
            </button>
          </div>

          <div className="mb-2 flex gap-2 text-xs">
            <span
              className={`rounded px-2 py-0.5 ${
                settings?.stt_local_available
                  ? 'bg-green-500/10 text-status-success'
                  : 'bg-red-500/10 text-status-error'
              }`}
              data-testid="stt-local-availability"
            >
              Local: {settings?.stt_local_available ? 'Available' : 'Not available'}
            </span>
            <span
              className={`rounded px-2 py-0.5 ${
                settings?.stt_cloud_available
                  ? 'bg-green-500/10 text-status-success'
                  : 'bg-red-500/10 text-status-error'
              }`}
              data-testid="stt-cloud-availability"
            >
              Cloud: {settings?.stt_cloud_available ? 'Available' : 'Not available'}
            </span>
          </div>

          {sttEngine === 'local' && (
            <>
              <div>
                <label
                  htmlFor="whisper-model-select"
                  className="mb-1 block text-sm font-medium text-text-primary"
                >
                  Whisper Model
                </label>
                <select
                  id="whisper-model-select"
                  value={whisperModel}
                  onChange={(e) => handleWhisperModelChange(e.target.value)}
                  className="w-full rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                  data-testid="whisper-model-select"
                >
                  {WHISPER_MODELS.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label
                  htmlFor="stt-device-select"
                  className="mb-1 block text-sm font-medium text-text-primary"
                >
                  Compute Device
                </label>
                <select
                  id="stt-device-select"
                  value={sttDevice}
                  onChange={(e) => void saveVoiceSettings({ stt_device: e.target.value })}
                  className="w-full rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                  data-testid="stt-device-select"
                >
                  {STT_DEVICES.map((d) => (
                    <option key={d} value={d} disabled={d === 'cuda' && !settings?.cuda_available}>
                      {d === 'cuda' && !settings?.cuda_available ? `${d} (unavailable)` : d}
                    </option>
                  ))}
                </select>
                {settings?.cuda_available && (
                  <p className="mt-1 text-xs text-status-success">
                    NVIDIA GPU detected — CUDA available
                  </p>
                )}
              </div>
            </>
          )}

          {sttEngine === 'cloud' && (
            <>
              <div>
                <label
                  htmlFor="deepgram-model-input"
                  className="mb-1 block text-sm font-medium text-text-primary"
                >
                  Deepgram Model
                </label>
                <input
                  id="deepgram-model-input"
                  type="text"
                  value={deepgramModel}
                  onChange={(e) => setDeepgramModel(e.target.value)}
                  placeholder="nova-2"
                  className="w-full rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                  data-testid="deepgram-model-input"
                />
              </div>
              <div>
                <label
                  htmlFor="deepgram-api-key-input"
                  className="mb-1 block text-sm font-medium text-text-primary"
                >
                  Deepgram API Key
                </label>
                <div className="flex gap-2">
                  <input
                    id="deepgram-api-key-input"
                    type={showDeepgramKey ? 'text' : 'password'}
                    value={deepgramKey}
                    onChange={(e) => setDeepgramKey(e.target.value)}
                    placeholder="Enter Deepgram API key"
                    className="flex-1 rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                    data-testid="deepgram-api-key-input"
                  />
                  <button
                    type="button"
                    onClick={() => setShowDeepgramKey((s) => !s)}
                    className="rounded border border-border-primary px-3 py-2 text-sm text-text-secondary hover:text-text-primary"
                    data-testid="deepgram-api-key-toggle"
                  >
                    {showDeepgramKey ? 'Hide' : 'Show'}
                  </button>
                </div>
              </div>
              <button
                type="button"
                onClick={handleDeepgramKeySave}
                disabled={saving || !deepgramKey.trim()}
                className="mt-2 rounded bg-accent px-4 py-2 text-sm text-white hover:opacity-90 disabled:opacity-50"
                data-testid="save-deepgram-key-button"
              >
                {saving ? 'Saving…' : 'Save Key'}
              </button>
              <button
                type="button"
                onClick={handleDeepgramModelSave}
                disabled={saving || !deepgramModel.trim()}
                className="ml-2 mt-2 rounded border border-border-primary px-4 py-2 text-sm text-text-primary hover:bg-bg-tertiary disabled:opacity-50"
                data-testid="save-deepgram-model-button"
              >
                {saving ? 'Saving…' : 'Save Model'}
              </button>
            </>
          )}
        </div>

        {/* TTS Section */}
        <div>
          <h3 className="mb-2 text-sm font-medium text-text-primary">Text-to-Speech</h3>

          <div className="mb-3 flex gap-2">
            <button
              type="button"
              onClick={() => handleTtsEngineChange('local')}
              className={`rounded border px-3 py-1.5 text-sm ${
                ttsEngine === 'local'
                  ? 'border-accent bg-accent text-text-inverse'
                  : 'border-border-primary text-text-secondary hover:text-text-primary'
              }`}
              data-testid="tts-local-toggle"
            >
              Local
            </button>
            <button
              type="button"
              onClick={() => handleTtsEngineChange('cloud')}
              className={`rounded border px-3 py-1.5 text-sm ${
                ttsEngine === 'cloud'
                  ? 'border-accent bg-accent text-text-inverse'
                  : 'border-border-primary text-text-secondary hover:text-text-primary'
              }`}
              data-testid="tts-cloud-toggle"
            >
              Cloud
            </button>
          </div>

          <div className="mb-2 flex gap-2 text-xs">
            <span
              className={`rounded px-2 py-0.5 ${
                settings?.tts_local_available
                  ? 'bg-green-500/10 text-status-success'
                  : 'bg-red-500/10 text-status-error'
              }`}
              data-testid="tts-local-availability"
            >
              Local: {settings?.tts_local_available ? 'Available' : 'Not available'}
            </span>
            <span
              className={`rounded px-2 py-0.5 ${
                settings?.tts_cloud_available
                  ? 'bg-green-500/10 text-status-success'
                  : 'bg-red-500/10 text-status-error'
              }`}
              data-testid="tts-cloud-availability"
            >
              Cloud: {settings?.tts_cloud_available ? 'Available' : 'Not available'}
            </span>
          </div>

          {ttsEngine === 'local' && (
            <div className="space-y-3">
              <div>
                <label
                  htmlFor="tts-device-select"
                  className="mb-1 block text-sm font-medium text-text-primary"
                >
                  Compute Device
                </label>
                <select
                  id="tts-device-select"
                  value={ttsDevice}
                  onChange={(e) => void saveVoiceSettings({ tts_device: e.target.value })}
                  className="w-full rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                  data-testid="tts-device-select"
                >
                  {TTS_DEVICES.map((d) => (
                    <option key={d} value={d} disabled={d === 'cuda' && !settings?.cuda_available}>
                      {d === 'cuda' && !settings?.cuda_available ? `${d} (unavailable)` : d}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <h4 className="mb-2 text-sm font-medium text-text-primary">Piper Voices</h4>
                {piperVoices.length === 0 && (
                  <p className="text-sm text-text-muted">No voices configured.</p>
                )}
                {piperVoices.length > 0 && (
                  <ul className="space-y-2">
                    {piperVoices.map((voice) => (
                      <li
                        key={voice.id}
                        className="flex items-center justify-between rounded border border-border-primary bg-bg-primary px-3 py-2"
                        data-testid={`piper-voice-${voice.id}`}
                      >
                        <div className="flex-1">
                          <span className="text-sm text-text-primary">{voice.name}</span>
                          <span className="ml-2 text-xs text-text-muted">{voice.path}</span>
                          {voice.id === activeVoiceId && (
                            <span className="ml-2 rounded bg-green-500/10 px-1.5 py-0.5 text-xs text-status-success">
                              Active
                            </span>
                          )}
                        </div>
                        <div className="flex gap-2">
                          {voice.id !== activeVoiceId && (
                            <button
                              type="button"
                              onClick={() => handleActivateVoice(voice.id)}
                              className="rounded border border-border-primary px-2 py-1 text-xs text-text-secondary hover:text-text-primary"
                              data-testid={`activate-voice-${voice.id}`}
                            >
                              Select
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => handleRemoveVoice(voice.id)}
                            className="rounded border border-red-500 px-2 py-1 text-xs text-status-error hover:bg-red-500/10"
                            data-testid={`remove-voice-${voice.id}`}
                          >
                            Remove
                          </button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="rounded border border-border-primary p-3">
                <h4 className="mb-2 text-sm font-medium text-text-primary">Add Voice</h4>
                <div className="space-y-2">
                  <div>
                    <label
                      htmlFor="new-voice-name"
                      className="mb-1 block text-xs text-text-secondary"
                    >
                      Name
                    </label>
                    <input
                      id="new-voice-name"
                      type="text"
                      value={newVoiceName}
                      onChange={(e) => setNewVoiceName(e.target.value)}
                      placeholder="e.g. en-us-lessac"
                      className="w-full rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                      data-testid="new-voice-name-input"
                    />
                  </div>
                  <div>
                    <label
                      htmlFor="new-voice-path"
                      className="mb-1 block text-xs text-text-secondary"
                    >
                      Voice File
                    </label>
                    <div className="flex gap-2">
                      <input
                        id="new-voice-path"
                        type="text"
                        value={newVoicePath}
                        onChange={(e) => setNewVoicePath(e.target.value)}
                        placeholder="Select a .onnx voice file"
                        readOnly
                        className="flex-1 rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                        data-testid="new-voice-path-input"
                      />
                      <button
                        type="button"
                        onClick={async () => {
                          const selected = await open({
                            filters: [{ name: 'Piper Voice', extensions: ['onnx'] }],
                          })
                          if (typeof selected === 'string') {
                            setNewVoicePath(selected)
                          }
                        }}
                        className="rounded border border-border-primary px-3 py-2 text-sm text-text-secondary hover:text-text-primary"
                        data-testid="browse-voice-button"
                      >
                        Browse
                      </button>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={handleAddVoice}
                    disabled={saving || !newVoiceName.trim() || !newVoicePath.trim()}
                    className="rounded bg-accent px-4 py-2 text-sm text-white hover:opacity-90 disabled:opacity-50"
                    data-testid="add-voice-button"
                  >
                    {saving ? 'Adding…' : 'Add Voice'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {ttsEngine === 'cloud' && (
            <>
              <div>
                <label
                  htmlFor="elevenlabs-voice-id-input"
                  className="mb-1 block text-sm font-medium text-text-primary"
                >
                  ElevenLabs Voice ID
                </label>
                <input
                  id="elevenlabs-voice-id-input"
                  type="text"
                  value={elevenlabsVoiceId}
                  onChange={(e) => setElevenlabsVoiceId(e.target.value)}
                  placeholder="Enter voice ID"
                  className="w-full rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                  data-testid="elevenlabs-voice-id-input"
                />
              </div>
              <div>
                <label
                  htmlFor="elevenlabs-api-key-input"
                  className="mb-1 block text-sm font-medium text-text-primary"
                >
                  ElevenLabs API Key
                </label>
                <div className="flex gap-2">
                  <input
                    id="elevenlabs-api-key-input"
                    type={showElevenlabsKey ? 'text' : 'password'}
                    value={elevenlabsKey}
                    onChange={(e) => setElevenlabsKey(e.target.value)}
                    placeholder="Enter ElevenLabs API key"
                    className="flex-1 rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                    data-testid="elevenlabs-api-key-input"
                  />
                  <button
                    type="button"
                    onClick={() => setShowElevenlabsKey((s) => !s)}
                    className="rounded border border-border-primary px-3 py-2 text-sm text-text-secondary hover:text-text-primary"
                    data-testid="elevenlabs-api-key-toggle"
                  >
                    {showElevenlabsKey ? 'Hide' : 'Show'}
                  </button>
                </div>
              </div>
              <button
                type="button"
                onClick={handleElevenlabsKeySave}
                disabled={saving || !elevenlabsKey.trim()}
                className="mt-2 rounded bg-accent px-4 py-2 text-sm text-white hover:opacity-90 disabled:opacity-50"
                data-testid="save-elevenlabs-key-button"
              >
                {saving ? 'Saving…' : 'Save Key'}
              </button>
              <button
                type="button"
                onClick={handleElevenlabsVoiceIdSave}
                disabled={saving || !elevenlabsVoiceId.trim()}
                className="ml-2 mt-2 rounded border border-border-primary px-4 py-2 text-sm text-text-primary hover:bg-bg-tertiary disabled:opacity-50"
                data-testid="save-elevenlabs-voice-id-button"
              >
                {saving ? 'Saving…' : 'Save Voice ID'}
              </button>
            </>
          )}
        </div>

        {/* Error banner */}
        {error && (
          <div
            className="rounded border border-red-500 bg-red-500/10 px-3 py-2 text-sm text-red-400"
            data-testid="voice-error"
          >
            {error}
          </div>
        )}

        {/* Success banner */}
        {success && (
          <div
            className="rounded border border-green-500 bg-green-500/10 px-3 py-2 text-sm text-green-400"
            data-testid="voice-success"
          >
            {success}
          </div>
        )}
      </div>
    </div>
  )
}
