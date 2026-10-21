import { defineConfig } from '@playwright/test'

const baseURL = process.env.BE002_FRONTEND_ORIGIN

if (!baseURL) {
  throw new Error('BE002_FRONTEND_ORIGIN is required for the deployed browser-auth smoke')
}

export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'line',
  use: {
    baseURL,
    headless: true,
    trace: 'off',
    screenshot: 'off',
    video: 'off',
  },
})
