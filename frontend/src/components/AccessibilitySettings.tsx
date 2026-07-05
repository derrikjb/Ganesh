import { useAccessibility, type FontSize } from '../contexts/AccessibilityContext'

const FONT_SIZES: FontSize[] = ['small', 'medium', 'large']

interface ToggleProps {
  id: string
  label: string
  description?: string
  checked: boolean
  onChange: (enabled: boolean) => void
}

function Toggle({ id, label, description, checked, onChange }: ToggleProps) {
  return (
    <div className="flex items-start justify-between gap-4 py-3">
      <div className="flex flex-col">
        <label htmlFor={id} className="text-sm font-medium text-text-primary">
          {label}
        </label>
        {description && (
          <span className="text-xs text-text-secondary mt-1">{description}</span>
        )}
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
          checked ? 'bg-accent' : 'bg-bg-tertiary'
        }`}
        data-testid={`toggle-${id}`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            checked ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </button>
    </div>
  )
}

interface AccessibilitySettingsProps {
  onClose?: () => void
}

export function AccessibilitySettings({ onClose }: AccessibilitySettingsProps) {
  const {
    textOnlyMode,
    fontSize,
    highContrast,
    reducedMotion,
    setTextOnlyMode,
    setFontSize,
    setHighContrast,
    setReducedMotion,
    reset,
  } = useAccessibility()

  return (
    <div
      className="flex flex-col gap-2 p-4 bg-bg-secondary rounded-lg border border-border max-w-md"
      data-testid="accessibility-settings"
      role="dialog"
      aria-label="Accessibility settings"
    >
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-base font-semibold text-text-primary">Accessibility</h2>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="text-text-muted hover:text-text-primary text-sm"
            aria-label="Close accessibility settings"
            data-testid="close-settings"
          >
            ×
          </button>
        )}
      </div>

      <Toggle
        id="text-only-mode"
        label="Text-only mode"
        description="Disable voice features and show text alternatives."
        checked={textOnlyMode}
        onChange={setTextOnlyMode}
      />

      <div className="py-3">
        <label
          htmlFor="font-size-select"
          className="text-sm font-medium text-text-primary"
        >
          Font size
        </label>
        <div className="flex gap-2 mt-2" role="group" aria-label="Font size">
          {FONT_SIZES.map((size) => (
            <button
              key={size}
              type="button"
              onClick={() => setFontSize(size)}
              className={`px-3 py-1 rounded-md text-sm capitalize transition-colors ${
                fontSize === size
                  ? 'bg-accent text-text-inverse'
                  : 'bg-bg-tertiary text-text-secondary hover:text-text-primary'
              }`}
              data-testid={`font-size-${size}`}
              aria-pressed={fontSize === size}
            >
              {size}
            </button>
          ))}
        </div>
      </div>

      <Toggle
        id="high-contrast"
        label="High contrast"
        description="Increase contrast between text and background."
        checked={highContrast}
        onChange={setHighContrast}
      />

      <Toggle
        id="reduced-motion"
        label="Reduced motion"
        description="Minimize animations and transitions."
        checked={reducedMotion}
        onChange={setReducedMotion}
      />

      <button
        type="button"
        onClick={reset}
        className="mt-2 self-start text-xs text-text-muted hover:text-text-primary"
        data-testid="reset-a11y"
      >
        Reset to defaults
      </button>
    </div>
  )
}
