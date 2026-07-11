import { useState, useEffect, useCallback, useRef } from 'react'
import { invoke } from '@tauri-apps/api/core'
import { sidecarFetch } from '../api'
import { useTTS } from '../hooks/useTTS'

interface VoiceSettingsResponse {
  stt_engine: 'local' | 'cloud'
  tts_engine: 'local' | 'cloud'
  whisper_model: string
  stt_language: string | null
  stt_device: string
  tts_device: string
  deepgram_model: string
  elevenlabs_voice_id: string
  tts_voice_name: string
  tts_voices: string[]
  stt_local_available: boolean
  stt_cloud_available: boolean
  tts_local_available: boolean
  tts_cloud_available: boolean
  cuda_available: boolean
  activation_mode: 'click_to_talk' | 'push_to_talk' | 'vad'
  input_device: string | null
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

async function saveApiKey(provider: string, apiKey: string): Promise<void> {
  const res = await sidecarFetch(`/api/voice/keys/${provider}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
  })
  if (!res.ok) throw new Error(`Failed to save API key: ${res.status}`)
}

export function VoiceSettings({ onClose }: VoiceSettingsProps) {
  const { ttsEnabled, setTtsEnabled, volume, setVolume, testChime, isSpeaking, outputDevices, outputDeviceId, setOutputDeviceId } = useTTS()
  const [settings, setSettings] = useState<VoiceSettingsResponse | null>(null)
  const [activationMode, setActivationMode] = useState<'click_to_talk' | 'push_to_talk' | 'vad'>('click_to_talk')
  const [pttHotkey, setPttHotkey] = useState('Control+Space')
  const [pttHotkeySaving, setPttHotkeySaving] = useState(false)
  const [capturing, setCapturing] = useState(false)
  const capturingRef = useRef(false)
  const capturedRef = useRef<string | null>(null)
  const heldModifierRef = useRef<string | null>(null)
  const [sttEngine, setSttEngine] = useState<'local' | 'cloud'>('local')
  const [ttsEngine, setTtsEngine] = useState<'local' | 'cloud'>('local')
  const [whisperModel, setWhisperModel] = useState('tiny')
  const [sttLanguage, setSttLanguage] = useState<string>('')
  const [sttDevice, setSttDevice] = useState('auto')
  const [ttsDevice, setTtsDevice] = useState('auto')
  const [deepgramModel, setDeepgramModel] = useState('nova-2')
  const [deepgramKey, setDeepgramKey] = useState('')
  const [elevenlabsKey, setElevenlabsKey] = useState('')
  const [elevenlabsVoiceId, setElevenlabsVoiceId] = useState('')
  const [showDeepgramKey, setShowDeepgramKey] = useState(false)
  const [showElevenlabsKey, setShowElevenlabsKey] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [devices, setDevices] = useState<Array<{ id: string; name: string; backend: string }>>([])
  const [inputDevice, setInputDevice] = useState<string>('')
  const [testing, setTesting] = useState(false)
  const [level, setLevel] = useState(0)

  const MODIFIER_KEYS = new Set(['Control', 'Shift', 'Alt', 'Meta'])
  const TAURI_MODIFIER_NAMES: Record<string, string> = {
    Control: 'Control',
    Shift: 'Shift',
    Alt: 'Alt',
    Meta: 'Super',
  }
  const KEY_DISPLAY: Record<string, string> = {
    ' ': 'Space',
    ArrowUp: 'Up',
    ArrowDown: 'Down',
    ArrowLeft: 'Left',
    ArrowRight: 'Right',
  }

  const handleHotkeyCapture = useCallback((e: React.KeyboardEvent) => {
    if (!capturingRef.current) return
    e.preventDefault()

    const isMod = MODIFIER_KEYS.has(e.key)
    const modName = isMod ? TAURI_MODIFIER_NAMES[e.key] : null
    if (modName) {
      heldModifierRef.current = modName
    }

    let combo: string
    if (heldModifierRef.current) {
      if (isMod) {
        combo = heldModifierRef.current
      } else {
        const keyName = KEY_DISPLAY[e.key] || e.key
        combo = `${heldModifierRef.current}+${keyName}`
      }
    } else if (!isMod) {
      const keyName = KEY_DISPLAY[e.key] || e.key
      combo = keyName
    } else {
      return
    }

    capturedRef.current = combo
    setPttHotkey(combo)
  }, [])

  const handleHotkeyRelease = useCallback(() => {
    if (!capturingRef.current) return
    const combo = capturedRef.current
    if (combo && combo !== pttHotkey) {
      setCapturing(false)
      capturingRef.current = false
      heldModifierRef.current = null
      void (async () => {
        setPttHotkeySaving(true)
        try {
          const result = await invoke<string>('set_ptt_hotkey', { hotkey: combo })
          setPttHotkey(result)
        } catch {
          setError('Failed to set hotkey. Use a valid combination.')
        } finally {
          setPttHotkeySaving(false)
        }
      })()
    }
  }, [pttHotkey])

  const startCapture = useCallback(() => {
    setCapturing(true)
    capturingRef.current = true
    capturedRef.current = null
    heldModifierRef.current = null
  }, [])

  const loadSettings = useCallback(async () => {
    try {
      const data = await fetchVoiceSettings()
      setSettings(data)
      setSttEngine(data.stt_engine)
      setTtsEngine(data.tts_engine)
      setWhisperModel(data.whisper_model)
      setSttLanguage(data.stt_language ?? '')
      setSttDevice(data.stt_device)
      setTtsDevice(data.tts_device)
      setDeepgramModel(data.deepgram_model)
      setElevenlabsVoiceId(data.elevenlabs_voice_id)
      setActivationMode(data.activation_mode)
      setInputDevice(data.input_device ?? '')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void loadSettings()
    invoke<string>('get_ptt_hotkey').then(setPttHotkey).catch(() => {})
    void fetchDevices()
  }, [loadSettings])

  const fetchDevices = useCallback(async () => {
    try {
      const res = await sidecarFetch('/api/voice/devices')
      if (res.ok) {
        const data = (await res.json()) as { devices: Array<{ id: string; name: string; backend: string }> }
        setDevices(data.devices)
      }
    } catch {
    }
  }, [])

  const handleInputDeviceChange = async (value: string) => {
    setInputDevice(value)
    setError(null)
    try {
      const updated = await saveVoiceSettings({ input_device: value || null })
      setSettings(updated)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleTestMicStart = async () => {
    setError(null)
    try {
      const res = await sidecarFetch('/api/voice/test-mic/start', { method: 'POST' })
      if (res.ok) {
        setTesting(true)
        setLevel(0)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const handleTestMicStop = async () => {
    try {
      await sidecarFetch('/api/voice/test-mic/stop', { method: 'POST' })
    } catch {
    }
    setTesting(false)
    setLevel(0)
  }

  useEffect(() => {
    if (!testing) return
    const interval = setInterval(async () => {
      try {
        const res = await sidecarFetch('/api/voice/test-mic/level')
        if (res.ok) {
          const data = (await res.json()) as { level: number; active: boolean }
          setLevel(data.level)
          if (!data.active) {
            setTesting(false)
            setLevel(0)
          }
        }
      } catch {
      }
    }, 100)
    return () => clearInterval(interval)
  }, [testing])

  useEffect(() => {
    return () => {
      if (testing) {
        void sidecarFetch('/api/voice/test-mic/stop', { method: 'POST' }).catch(() => {})
      }
    }
  }, [testing])

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
      window.dispatchEvent(new CustomEvent('ganesh:voice-settings-changed'))
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
                <button
                  id="ptt-hotkey-input"
                  type="button"
                  onClick={startCapture}
                  onKeyDown={(e) => {
                    if (capturingRef.current) {
                      handleHotkeyCapture(e)
                    } else if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      startCapture()
                    }
                  }}
                  onKeyUp={handleHotkeyRelease}
                  onBlur={() => {
                    if (capturingRef.current) {
                      setCapturing(false)
                      capturingRef.current = false
                    }
                  }}
                  className={`flex-1 rounded border px-3 py-2 text-sm ${
                    capturing
                      ? 'border-accent bg-accent/10 text-accent'
                      : 'border-border-primary bg-bg-primary text-text-primary'
                  }`}
                  data-testid="ptt-hotkey-input"
                >
                  {capturing ? 'Press keys…' : pttHotkey || 'Click to set'}
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    if (capturedRef.current) {
                      setPttHotkeySaving(true)
                      try {
                        const result = await invoke<string>('set_ptt_hotkey', { hotkey: capturedRef.current })
                        setPttHotkey(result)
                      } catch {
                        setError('Failed to set hotkey. Use a valid combination like Control+Space or Alt+R.')
                      } finally {
                        setPttHotkeySaving(false)
                      }
                    }
                  }}
                  disabled={pttHotkeySaving || !capturedRef.current}
                  className="rounded border border-border-primary px-3 py-2 text-sm text-text-secondary hover:text-text-primary"
                  data-testid="ptt-hotkey-save"
                >
                  {pttHotkeySaving ? 'Saving…' : 'Set'}
                </button>
              </div>
              <p className="mt-1 text-xs text-text-muted">
                Click the field, then press a key combination (e.g. Ctrl+K, Alt+Space, or a single key like F5).
                The secondary key updates live while holding a modifier. Lift all keys to finalize.
              </p>
            </div>
          )}
        </div>

        {/* Microphone Section */}
        <div>
          <h3 className="mb-2 text-sm font-medium text-text-primary">Microphone</h3>
          <div className="mb-3">
            <label htmlFor="mic-device-select" className="mb-1 block text-sm font-medium text-text-primary">
              Input Device
            </label>
            <select
              id="mic-device-select"
              value={inputDevice}
              onChange={(e) => void handleInputDeviceChange(e.target.value)}
              className="w-full rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
              data-testid="mic-device-select"
            >
              <option value="">Default</option>
              {devices.map((device) => (
                <option key={device.id} value={device.id}>
                  {device.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <button
              type="button"
              onClick={testing ? handleTestMicStop : handleTestMicStart}
              className="rounded border border-border-primary px-3 py-2 text-sm text-text-secondary hover:text-text-primary"
              data-testid="test-mic-button"
            >
              {testing ? 'Stop Test' : 'Test Microphone'}
            </button>
            {testing && (
              <div className="mt-2">
                <div className="w-full h-3 rounded bg-bg-tertiary overflow-hidden">
                  <div
                    className="h-full bg-status-success transition-all duration-75"
                    style={{ width: `${level * 100}%` }}
                  />
                </div>
                <div className="mt-1 flex items-center justify-between">
                  <p className="text-xs text-text-muted">{Math.round(level * 100)}%</p>
                  {level < 0.01 && (
                    <p className="text-xs text-status-warning">No input detected</p>
                  )}
                </div>
              </div>
            )}
          </div>
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
                  onChange={async (e) => {
                    const updated = await saveVoiceSettings({ stt_device: e.target.value })
                    setSettings(updated)
                    setSttDevice(updated.stt_device)
                  }}
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
              <div>
                <label
                  htmlFor="stt-language-select"
                  className="mb-1 block text-sm font-medium text-text-primary"
                >
                  Language
                </label>
                <select
                  id="stt-language-select"
                  value={sttLanguage}
                  onChange={async (e) => {
                    const updated = await saveVoiceSettings({ stt_language: e.target.value || null })
                    setSettings(updated)
                    setSttLanguage(e.target.value || '')
                  }}
                  className="w-full rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                  data-testid="stt-language-select"
                >
                  <option value="">Auto-detect</option>
                  <option value="en">English</option>
                  <option value="es">Spanish</option>
                  <option value="fr">French</option>
                  <option value="de">German</option>
                  <option value="it">Italian</option>
                  <option value="pt">Portuguese</option>
                  <option value="ru">Russian</option>
                  <option value="ja">Japanese</option>
                  <option value="ko">Korean</option>
                  <option value="zh">Chinese</option>
                  <option value="ar">Arabic</option>
                  <option value="hi">Hindi</option>
                  <option value="tr">Turkish</option>
                  <option value="nl">Dutch</option>
                  <option value="pl">Polish</option>
                  <option value="sv">Swedish</option>
                </select>
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
                  onChange={async (e) => {
                    const updated = await saveVoiceSettings({ tts_device: e.target.value })
                    setSettings(updated)
                    setTtsDevice(updated.tts_device)
                  }}
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
                <label
                  htmlFor="tts-voice-select"
                  className="mb-1 block text-sm font-medium text-text-primary"
                >
                  Voice
                </label>
                <select
                  id="tts-voice-select"
                  value={settings?.tts_voice_name ?? 'af_heart'}
                  onChange={async (e) => {
                    const updated = await saveVoiceSettings({ tts_voice_name: e.target.value })
                    setSettings(updated)
                  }}
                  className="w-full rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                  data-testid="tts-voice-select"
                >
                  {(settings?.tts_voices ?? ['af_heart']).map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>
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

        <div className="mt-4 border-t border-border-primary pt-4">
          <h4 className="mb-3 text-sm font-medium text-text-primary">TTS Output</h4>

          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-text-primary">
              Text-to-Speech
            </label>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setTtsEnabled(!ttsEnabled)}
                className={`rounded border px-3 py-1.5 text-sm ${
                  ttsEnabled
                    ? 'border-accent bg-accent/10 text-accent'
                    : 'border-border-primary text-text-muted'
                }`}
                data-testid="tts-toggle"
              >
                {ttsEnabled ? 'Enabled' : 'Disabled'}
              </button>
              <span className="text-xs text-text-muted">
                Automatically speak assistant responses
              </span>
            </div>
          </div>

          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-text-primary">
              Volume
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={volume}
                onChange={(e) => setVolume(Number(e.target.value))}
                className="flex-1"
                data-testid="tts-volume-slider"
              />
              <span className="w-12 text-sm text-text-muted">
                {Math.round(volume * 100)}%
              </span>
              <button
                type="button"
                onClick={testChime}
                disabled={isSpeaking}
                className="rounded border border-border-primary px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary disabled:opacity-50"
                data-testid="tts-test-chime"
              >
                🔔
              </button>
            </div>
          </div>

          {outputDevices.length > 0 && (
            <div className="mb-4">
              <label className="mb-1 block text-sm font-medium text-text-primary" htmlFor="output-device-select">
                Output Device
              </label>
              <select
                id="output-device-select"
                value={outputDeviceId ?? ''}
                onChange={(e) => setOutputDeviceId(e.target.value || null)}
                className="w-full rounded border border-border-primary bg-bg-primary px-3 py-2 text-sm text-text-primary"
                data-testid="output-device-select"
              >
                <option value="">Default</option>
                {outputDevices.map((d) => (
                  <option key={d.deviceId} value={d.deviceId}>
                    {d.label || `Device ${d.deviceId.slice(0, 8)}`}
                  </option>
                ))}
              </select>
            </div>
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
