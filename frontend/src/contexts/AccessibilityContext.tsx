import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react'
import type { SpeedMultiplier } from '../hooks/useNaturalPacing'

export type FontSize = 'small' | 'medium' | 'large'

export interface AccessibilityState {
  textOnlyMode: boolean
  fontSize: FontSize
  highContrast: boolean
  reducedMotion: boolean
  naturalPacingEnabled: boolean
  naturalPacingSpeed: SpeedMultiplier
}

export interface AccessibilityContextValue extends AccessibilityState {
  setTextOnlyMode: (enabled: boolean) => void
  setFontSize: (size: FontSize) => void
  setHighContrast: (enabled: boolean) => void
  setReducedMotion: (enabled: boolean) => void
  setNaturalPacingEnabled: (enabled: boolean) => void
  setNaturalPacingSpeed: (speed: SpeedMultiplier) => void
  reset: () => void
}

const STORAGE_KEY = 'ganesh.a11y'

const DEFAULT_STATE: AccessibilityState = {
  textOnlyMode: false,
  fontSize: 'medium',
  highContrast: false,
  reducedMotion: false,
  naturalPacingEnabled: true,
  naturalPacingSpeed: 1,
}

const AccessibilityContext = createContext<AccessibilityContextValue | undefined>(undefined)

function readStoredState(): AccessibilityState {
  if (typeof window === 'undefined') return DEFAULT_STATE
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_STATE
    const parsed = JSON.parse(raw) as Partial<AccessibilityState>
    const speed = parsed.naturalPacingSpeed
    const validSpeed: SpeedMultiplier =
      speed === 0.5 || speed === 1 || speed === 2 || speed === 'instant' ? speed : 1
    return {
      textOnlyMode: Boolean(parsed.textOnlyMode),
      fontSize:
        parsed.fontSize === 'small' || parsed.fontSize === 'large'
          ? parsed.fontSize
          : 'medium',
      highContrast: Boolean(parsed.highContrast),
      reducedMotion: Boolean(parsed.reducedMotion),
      naturalPacingEnabled: parsed.naturalPacingEnabled !== undefined ? Boolean(parsed.naturalPacingEnabled) : true,
      naturalPacingSpeed: validSpeed,
    }
  } catch {
    return DEFAULT_STATE
  }
}

function writeStoredState(state: AccessibilityState): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // localStorage may be unavailable (private mode, quota); fail silently.
  }
}

interface AccessibilityProviderProps {
  children: ReactNode
}

export function AccessibilityProvider({ children }: AccessibilityProviderProps) {
  const [state, setState] = useState<AccessibilityState>(() => readStoredState())

  useEffect(() => {
    writeStoredState(state)
  }, [state])

  useEffect(() => {
    const root = document.documentElement
    root.setAttribute('data-text-only', state.textOnlyMode ? 'on' : 'off')
    root.setAttribute('data-font-size', state.fontSize)
    root.setAttribute('data-contrast', state.highContrast ? 'high' : 'normal')
    root.setAttribute('data-motion', state.reducedMotion ? 'reduced' : 'normal')
  }, [state])

  const setTextOnlyMode = useCallback((enabled: boolean) => {
    setState((prev) => ({ ...prev, textOnlyMode: enabled }))
  }, [])

  const setFontSize = useCallback((size: FontSize) => {
    setState((prev) => ({ ...prev, fontSize: size }))
  }, [])

  const setHighContrast = useCallback((enabled: boolean) => {
    setState((prev) => ({ ...prev, highContrast: enabled }))
  }, [])

  const setReducedMotion = useCallback((enabled: boolean) => {
    setState((prev) => ({ ...prev, reducedMotion: enabled }))
  }, [])

  const setNaturalPacingEnabled = useCallback((enabled: boolean) => {
    setState((prev) => ({ ...prev, naturalPacingEnabled: enabled }))
  }, [])

  const setNaturalPacingSpeed = useCallback((speed: SpeedMultiplier) => {
    setState((prev) => ({ ...prev, naturalPacingSpeed: speed }))
  }, [])

  const reset = useCallback(() => {
    setState(DEFAULT_STATE)
  }, [])

  const value: AccessibilityContextValue = {
    ...state,
    setTextOnlyMode,
    setFontSize,
    setHighContrast,
    setReducedMotion,
    setNaturalPacingEnabled,
    setNaturalPacingSpeed,
    reset,
  }

  return (
    <AccessibilityContext.Provider value={value}>
      {children}
    </AccessibilityContext.Provider>
  )
}

export function useAccessibility(): AccessibilityContextValue {
  const ctx = useContext(AccessibilityContext)
  if (ctx === undefined) {
    throw new Error('useAccessibility must be used within an AccessibilityProvider')
  }
  return ctx
}
