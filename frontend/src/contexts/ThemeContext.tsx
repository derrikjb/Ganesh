import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'

export type ThemeName = 'dark' | 'midnight' | 'ocean' | 'forest' | 'custom'

export interface ThemeCustomizations {
  accentColor?: string
  chatUserColor?: string
  chatAssistantColor?: string
  borderStyle?: 'rounded' | 'square'
}

export interface ThemeContextValue {
  theme: ThemeName
  customizations: ThemeCustomizations
  setTheme: (name: ThemeName) => void
  setCustomizations: (overrides: ThemeCustomizations) => void
  resetCustomizations: () => void
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined)

const STORAGE_KEY = 'ganesh-theme'
const CUSTOM_KEY = 'ganesh-theme-customizations'

function loadSavedTheme(): { theme: ThemeName; customizations: ThemeCustomizations } {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    const savedCustom = localStorage.getItem(CUSTOM_KEY)
    const theme: ThemeName = (saved as ThemeName) || 'dark'
    const customizations: ThemeCustomizations = savedCustom ? JSON.parse(savedCustom) : {}
    return { theme, customizations }
  } catch {
    return { theme: 'dark', customizations: {} }
  }
}

function applyThemeToDOM(theme: ThemeName, customizations: ThemeCustomizations) {
  document.documentElement.setAttribute('data-theme', theme)
  document.documentElement.style.colorScheme = 'dark'

  const root = document.documentElement.style

  if (customizations.accentColor) {
    root.setProperty('--accent', customizations.accentColor)
  }
  if (customizations.chatUserColor) {
    root.setProperty('--chat-user-bg', customizations.chatUserColor)
  }
  if (customizations.chatAssistantColor) {
    root.setProperty('--chat-assistant-bg', customizations.chatAssistantColor)
  }
  if (customizations.borderStyle === 'square') {
    root.setProperty('--chat-bubble-radius', 'var(--radius-sm)')
  } else if (customizations.borderStyle === 'rounded') {
    root.setProperty('--chat-bubble-radius', 'var(--radius-lg)')
  }
}

interface ThemeProviderProps {
  children: ReactNode
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const saved = loadSavedTheme()
  const [theme, setThemeState] = useState<ThemeName>(saved.theme)
  const [customizations, setCustomizationsState] = useState<ThemeCustomizations>(saved.customizations)

  useEffect(() => {
    applyThemeToDOM(theme, customizations)
  }, [theme, customizations])

  const setTheme = useCallback((name: ThemeName) => {
    setThemeState(name)
    try {
      localStorage.setItem(STORAGE_KEY, name)
    } catch {
      // localStorage unavailable
    }
  }, [])

  const setCustomizations = useCallback((overrides: ThemeCustomizations) => {
    setCustomizationsState((prev) => {
      const next = { ...prev, ...overrides }
      try {
        localStorage.setItem(CUSTOM_KEY, JSON.stringify(next))
      } catch {
        // localStorage unavailable
      }
      return next
    })
  }, [])

  const resetCustomizations = useCallback(() => {
    setCustomizationsState({})
    try {
      localStorage.removeItem(CUSTOM_KEY)
    } catch {
      // localStorage unavailable
    }
  }, [])

  return (
    <ThemeContext.Provider value={{ theme, customizations, setTheme, setCustomizations, resetCustomizations }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext)
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider')
  }
  return context
}
