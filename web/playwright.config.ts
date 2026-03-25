import { defineConfig } from '@playwright/test';

const useExternalServer = process.env.PLAYWRIGHT_NO_WEBSERVER === '1';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    headless: true,
  },
  webServer: useExternalServer
    ? undefined
    : {
        command: 'npm run dev',
        port: 5173,
        reuseExistingServer: true,
        timeout: 30_000,
      },
});
