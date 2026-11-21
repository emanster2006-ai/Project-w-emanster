import { defineConfig } from "@playwright/test";

// The API is mocked in the tests, so this needs only the built frontend.
// Locally set PW_CHANNEL=chrome to use an installed Chrome instead of downloading Chromium.
export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: "http://localhost:3127",
    channel: process.env.PW_CHANNEL || undefined,
  },
  webServer: {
    command: "npx next start -p 3127",
    url: "http://localhost:3127",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
