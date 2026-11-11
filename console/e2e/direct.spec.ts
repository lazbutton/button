import type { Page } from "@playwright/test";
import { antenne, expect, seConnecter, test } from "./banc.ts";

// « Passer en direct », ouvert à tout compte : l'adresse du direct vient des
// réglages de la station, par GET /station/harbor.json, jamais d'une adresse
// en repli. Le banc a une station d'exemple en radio.example
// (engine/tests/e2e/seed.py).

/** Ce que Quart répond à une route qu'il ne connaît pas : la description par défaut de werkzeug. */
const ROUTE_ABSENTE = {
  error:
    "The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.",
};

/** Une station qui n'a pas encore réglé l'hôte de son direct. */
const SANS_HOTE = { host: null, port: 6800, mount: "/stream" };

async function ouvrirLeDirect(page: Page) {
  await antenne(page).getByRole("button", { name: "Passer en direct" }).click();
  const panneau = page.getByRole("dialog", { name: "Passer en direct" });
  await expect(panneau).toBeVisible();
  return panneau;
}

test("l’adresse réglée du direct se copie, pour un animateur aussi", async ({ page }) => {
  await seConnecter(page, "animateur");
  const panneau = await ouvrirLeDirect(page);
  await expect(panneau.getByRole("button", { name: "Copier l’adresse : radio.example" })).toBeVisible();
  // Port et mount non réglés : ceux du logiciel.
  await expect(panneau.getByRole("button", { name: "Copier le port : 6800" })).toBeVisible();
  await expect(panneau.getByRole("button", { name: "Copier le mount : /stream" })).toBeVisible();
});

test("sans hôte réglé, le panneau cache l’adresse, et mène l’admin au réglage", async ({ page }) => {
  await page.route("**/station/harbor.json", (route) => route.fulfill({ json: SANS_HOTE }));
  await seConnecter(page, "admin");
  const panneau = await ouvrirLeDirect(page);
  await expect(panneau.getByText("L’adresse du direct n’est pas encore réglée.")).toBeVisible();
  await expect(panneau.getByRole("button", { name: /^Copier (l’adresse|le port|le mount)/ })).toHaveCount(0);

  await panneau.getByRole("link", { name: "La régler" }).click();
  await expect(panneau).toBeHidden();
  await expect(page.getByRole("tab", { name: "Station", selected: true })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Hôte", exact: true })).toBeVisible();
});

test("sans hôte réglé, un animateur apprend qui le règle", async ({ page }) => {
  await page.route("**/station/harbor.json", (route) => route.fulfill({ json: SANS_HOTE }));
  await seConnecter(page, "animateur");
  const panneau = await ouvrirLeDirect(page);
  await expect(
    panneau.getByText("L’adresse du direct n’est pas encore réglée. Un admin la règle dans Réglages → Station."),
  ).toBeVisible();
  await expect(panneau.getByRole("link", { name: "La régler" })).toHaveCount(0);
});

test("moteur sans la route : le panneau dit de le mettre à jour", async ({ page }) => {
  await page.route("**/station/harbor.json", (route) => route.fulfill({ status: 404, json: ROUTE_ABSENTE }));
  await seConnecter(page, "animateur");
  const panneau = await ouvrirLeDirect(page);
  await expect(panneau.getByText("Mets à jour le moteur pour lire l’adresse du direct.")).toBeVisible();
  // Le 404 ne s'affiche pas en anglais.
  await expect(panneau.getByText(/requested URL/)).toHaveCount(0);
});
