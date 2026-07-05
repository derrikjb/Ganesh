import { useState } from 'react'
import { useTheme, type ThemeName, type ThemeCustomizations } from '../contexts/ThemeContext'

const PRESETS: { name: ThemeName; label: string; accent: string }[] = [
  { name: 'dark', label: 'Default', accent: '#3b82f6' },
  { name: 'midnight', label: 'Midnight', accent: '#58a6ff' },
  { name: 'ocean', label: 'Ocean', accent: '#64ffda' },
  { name: 'forest', label: 'Forest', accent: '#4ade80' },
]

function ThemePreview({ themeName, accent, active, onClick }: { themeName: ThemeName; accent: string; active: boolean; onClick: () => void }) {
  return (
    <div
      className={`relative flex flex-col gap-1.5 rounded-lg p-3 border-2 transition-all cursor-pointer ${
        active ? 'border-accent bg-bg-secondary' : 'border-border bg-bg-primary hover:border-border-focus'
      }`}
      style={{ '--preview-accent': accent } as React.CSSProperties}
      data-testid={`theme-preview-${themeName}`}
      onClick={onClick}
    >
      <div className="flex items-center gap-2">
        <div
          className="w-4 h-4 rounded-full"
          style={{ backgroundColor: accent }}
        />
        <span className="text-xs text-text-primary font-medium">{themeName === 'dark' ? 'Default' : themeName.charAt(0).toUpperCase() + themeName.slice(1)}</span>
      </div>
      <div className="flex gap-1.5">
        <div className="flex-1 h-3 rounded" style={{ backgroundColor: accent, opacity: 0.8 }} />
        <div className="flex-1 h-3 rounded bg-bg-tertiary" />
      </div>
    </div>
  )
}

function ColorPicker({ label, value, onChange }: { label: string; value: string; onChange: (color: string) => void }) {
  return (
    <div className="flex items-center gap-3">
      <label className="text-xs text-text-secondary min-w-[80px]">{label}</label>
      <input
        type="color"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-8 h-8 rounded cursor-pointer border border-border bg-transparent"
        data-testid={`color-picker-${label.toLowerCase().replace(/\s+/g, '-')}`}
      />
      <span className="text-xs text-text-muted font-mono">{value}</span>
    </div>
  )
}

export function ThemeSwitcher() {
  const { theme, customizations, setTheme, setCustomizations, resetCustomizations } = useTheme()
  const [showCustom, setShowCustom] = useState(false)

  const accentColor = customizations.accentColor || PRESETS.find((p) => p.name === theme)?.accent || '#3b82f6'
  const chatUserColor = customizations.chatUserColor || accentColor
  const chatAssistantColor = customizations.chatAssistantColor || '#262626'

  const handlePresetSelect = (name: ThemeName) => {
    setTheme(name)
    if (name !== 'custom') {
      resetCustomizations()
    }
  }

  const handleColorChange = (key: keyof ThemeCustomizations, value: string) => {
    if (theme !== 'custom') {
      setTheme('custom')
    }
    setCustomizations({ [key]: value })
  }

  const handleBorderStyle = (style: 'rounded' | 'square') => {
    if (theme !== 'custom') {
      setTheme('custom')
    }
    setCustomizations({ borderStyle: style })
  }

  return (
    <div className="flex flex-col gap-4 p-4 bg-bg-secondary rounded-lg border border-border" data-testid="theme-switcher">
      <h3 className="text-sm font-semibold text-text-primary">Theme</h3>

      <div className="grid grid-cols-2 gap-2">
        {PRESETS.map((preset) => (
          <ThemePreview
            key={preset.name}
            themeName={preset.name}
            accent={preset.accent}
            active={theme === preset.name}
            onClick={() => handlePresetSelect(preset.name)}
          />
        ))}
      </div>

      <button
        onClick={() => setShowCustom(!showCustom)}
        className="text-xs text-accent hover:text-accent-hover transition-colors text-left"
        data-testid="toggle-custom"
      >
        {showCustom ? 'Hide' : 'Show'} custom options
      </button>

      {showCustom && (
        <div className="flex flex-col gap-3 pt-2 border-t border-border">
          <ColorPicker
            label="Accent"
            value={accentColor}
            onChange={(c) => handleColorChange('accentColor', c)}
          />
          <ColorPicker
            label="User Bubble"
            value={chatUserColor}
            onChange={(c) => handleColorChange('chatUserColor', c)}
          />
          <ColorPicker
            label="Assistant Bubble"
            value={chatAssistantColor}
            onChange={(c) => handleColorChange('chatAssistantColor', c)}
          />

          <div className="flex items-center gap-3">
            <label className="text-xs text-text-secondary min-w-[80px]">Bubble Style</label>
            <div className="flex gap-2">
              <button
                onClick={() => handleBorderStyle('rounded')}
                className={`px-3 py-1 text-xs rounded-md transition-colors ${
                  customizations.borderStyle !== 'square'
                    ? 'bg-accent text-text-inverse'
                    : 'bg-bg-tertiary text-text-secondary hover:text-text-primary'
                }`}
                data-testid="border-style-rounded"
              >
                Rounded
              </button>
              <button
                onClick={() => handleBorderStyle('square')}
                className={`px-3 py-1 text-xs rounded-sm transition-colors ${
                  customizations.borderStyle === 'square'
                    ? 'bg-accent text-text-inverse'
                    : 'bg-bg-tertiary text-text-secondary hover:text-text-primary'
                }`}
                data-testid="border-style-square"
              >
                Square
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
