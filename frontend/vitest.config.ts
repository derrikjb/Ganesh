import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    pool: 'threads',
    poolOptions: {
      threads: { singleThread: true },
    },
    include: ['src/**/*.test.{ts,tsx}'],
    exclude: ['node_modules/', 'tests/integration/', 'tests/fixtures/'],
  },
})
