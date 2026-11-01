import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests: a real browser against the full running stack
 * (Angular + API + worker + PostgreSQL + Redis).
 *
 *   docker compose up -d --build     # start the stack
 *   npx playwright install chromium  # once
 *   npm run e2e                      # run (E2E_BASE_URL defaults to http://localhost:8080)
 *   npx playwright show-report       # open the HTML report after a failure
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false, // the tests share one database; keep them predictable
  workers: 1,
  retries: process.env['CI'] ? 1 : 0,
  reporter: process.env['CI'] ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env['E2E_BASE_URL'] ?? 'http://localhost:8080',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
