import { defineConfig, devices } from "@playwright/test";

// Les parcours de la console dans un vrai navigateur. scripts/e2e.sh monte le
// banc (moteur de démo, faux services, build de la console servi par vite
// preview), puis lance Playwright avec ses adresses : ./scripts/e2e.sh, pas
// npx playwright test.
const baseURL = process.env.E2E_CONSOLE;
if (!baseURL) throw new Error("E2E_CONSOLE manque : lancer les parcours avec ./scripts/e2e.sh.");

export default defineConfig({
  testDir: "e2e",
  outputDir: process.env.E2E_RESULTATS || "test-results",
  // Les parcours partagent le moteur de démo, et la machine sa mémoire :
  // un seul navigateur à la fois.
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  reporter: "list",
  use: {
    baseURL,
    locale: "fr-FR",
    timezoneId: "Europe/Paris",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
