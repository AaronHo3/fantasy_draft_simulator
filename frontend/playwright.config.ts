import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { defineConfig } from '@playwright/test'

// Dedicated ports so e2e never collides with a `make dev` backend on 8000 / frontend on 5173.
const backendPort = Number(process.env.E2E_BACKEND_PORT ?? 8010)
const frontendPort = Number(process.env.E2E_FRONTEND_PORT ?? 5174)
const backendUrl = `http://127.0.0.1:${backendPort}`
const frontendUrl = `http://127.0.0.1:${frontendPort}`
const dataDir = mkdtempSync(join(tmpdir(), 'copilot-e2e-'))

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 10_000 },
  retries: 0,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: frontendUrl,
    trace: 'retain-on-failure',
    viewport: { width: 1440, height: 900 },
  },
  webServer: [
    {
      command: `uv run uvicorn app.main:app --host 127.0.0.1 --port ${backendPort}`,
      cwd: '../backend',
      url: `${backendUrl}/api/health`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: { ...process.env, COPILOT_DATA_DIR: dataDir },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${frontendPort} --strictPort`,
      url: frontendUrl,
      timeout: 60_000,
      reuseExistingServer: false,
      env: { ...process.env, COPILOT_BACKEND: backendUrl },
    },
  ],
})
