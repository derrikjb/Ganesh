import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

describe('Frontend Project Structure', () => {
  it('should have critical frontend files', () => {
    const frontendRoot = path.resolve(__dirname, '../..')
    const files = [
      'src/App.tsx',
      'src/main.tsx',
      'index.html',
      'vite.config.ts',
      'package.json',
      'tsconfig.json'
    ]
    
    files.forEach(file => {
      const filePath = path.join(frontendRoot, file)
      expect(fs.existsSync(filePath)).toBe(true)
    })
  })
})
