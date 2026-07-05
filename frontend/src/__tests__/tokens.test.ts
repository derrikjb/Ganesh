import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

describe('Design Tokens', () => {
  const tokensPath = path.resolve(__dirname, '../styles/tokens.css')
  const themePath = path.resolve(__dirname, '../styles/theme.css')

  it('tokens.css file exists', () => {
    expect(fs.existsSync(tokensPath)).toBe(true)
  })

  it('theme.css file exists', () => {
    expect(fs.existsSync(themePath)).toBe(true)
  })

  it('defines required color tokens', () => {
    const content = fs.readFileSync(tokensPath, 'utf-8')
    const requiredColors = [
      '--color-bg-primary',
      '--color-bg-secondary',
      '--color-text-primary',
      '--color-accent',
      '--color-border',
    ]
    requiredColors.forEach((token) => {
      expect(content).toContain(token)
    })
  })

  it('defines spacing tokens from xs to xl', () => {
    const content = fs.readFileSync(tokensPath, 'utf-8')
    const requiredSpacing = [
      '--space-xs',
      '--space-sm',
      '--space-md',
      '--space-lg',
      '--space-xl',
    ]
    requiredSpacing.forEach((token) => {
      expect(content).toContain(token)
    })
  })

  it('defines typography tokens', () => {
    const content = fs.readFileSync(tokensPath, 'utf-8')
    expect(content).toContain('--font-sans')
    expect(content).toContain('--font-mono')
    expect(content).toContain('--text-base')
  })

  it('defines radius and transition tokens', () => {
    const content = fs.readFileSync(tokensPath, 'utf-8')
    expect(content).toContain('--radius-md')
    expect(content).toContain('--transition-base')
  })

  it('theme.css maps semantic variables to tokens', () => {
    const content = fs.readFileSync(themePath, 'utf-8')
    expect(content).toContain('--bg-primary: var(--color-bg-primary)')
    expect(content).toContain('--text-primary: var(--color-text-primary)')
    expect(content).toContain('--accent: var(--color-accent)')
    expect(content).toContain('--border: var(--color-border)')
  })

  it('theme.css supports data-theme selector', () => {
    const content = fs.readFileSync(themePath, 'utf-8')
    expect(content).toContain("[data-theme='dark']")
  })
})
