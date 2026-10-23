import { configDefaults, defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'jsdom',
    exclude: [...configDefaults.exclude, 'tests/browser/**'],
    setupFiles: ['./src/test/setup.ts'],
  },
})
