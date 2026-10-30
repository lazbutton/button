import type { Page } from "@playwright/test";
import { DEFAULT_SOURCE_URL } from "../src/lib/brand.ts";
import { antenne, expect, seConnecter, tenirLAntenne, test } from "./banc.ts";

// La barre du haut, la même sur toutes les pages : ce qui passe, l'état de
// l'antenne, le casque et le compte.

const barre = (page: Page) => page.getByRole("banner");
const casque = (page: Page) => barre(page).getByRole("button", { name: /^(Écouter au casque|Arrêter l’écoute)/ });
const echapper = (texte: string) => texte.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

test("la barre dit ce qui passe, et l’état de l’antenne s’ouvre en détail", async ({ page }) => {
  await seConnecter(page, "animateur");
  await tenirLAntenne(page);

  // Le titre à l'antenne est le même que sur le pupitre.
  const titre = (await antenne(page).getByRole("paragraph").first().textContent()) ?? "";
  const enCours = barre(page).getByRole("link", { name: /^À l’antenne : / });
  await expect(enCours).toHaveAccessibleName(new RegExp(`^À l’antenne : ${echapper(titre)}[,.]`));

  const etat = barre(page).getByRole("button", { name: /^Antenne : / });
  await expect(etat).toHaveAccessibleName(/^Antenne : En onde, .+\. Santé : tout va bien\.$/);
  await etat.click();
  const detail = page.getByRole("dialog");
  await expect(detail.getByText("État de l’antenne")).toBeVisible();
  const sante = detail.getByRole("list", { name: "Santé antenne" }).getByRole("listitem");
  await expect(sante).toHaveCount(6);
  await expect(sante.filter({ hasText: "Moteur" })).toContainText("OK");
  // Le diagnostic de l'automate est réservé à l'admin.
  await expect(detail.getByRole("link", { name: "Diagnostic automate" })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(detail).toBeHidden();
  await expect(etat).toBeFocused();

  // D'une autre page, le titre ramène au pupitre.
  await page.getByRole("navigation", { name: "Console" }).getByRole("link", { name: "Conducteur" }).click();
  await expect(page).toHaveURL(/\/conducteur$/);
  await enCours.click();
  await expect(page).toHaveURL(/\/antenne$/);
  await expect(antenne(page)).toBeVisible();
});

test("écouter l’antenne au casque, puis arrêter", async ({ page }) => {
  await seConnecter(page, "animateur");
  await expect(casque(page)).toHaveAccessibleName("Écouter au casque : Antenne publique");
  await expect(casque(page)).toHaveAttribute("aria-pressed", "false");

  await casque(page).click();
  await expect(casque(page)).toHaveAttribute("aria-pressed", "true");
  await expect(casque(page)).toHaveAccessibleName(/^Arrêter l’écoute\./);

  await casque(page).click();
  await expect(casque(page)).toHaveAttribute("aria-pressed", "false");
  await expect(casque(page)).toHaveAccessibleName("Écouter au casque : Antenne publique");
});

test.fixme("un flux muet au casque : la console le dit", async ({ page }) => {
  // Défaut de la console : le banc coupe le flux, et le casque n'entend rien.
  // Le bouton dit pourtant « Arrêter l’écoute. Couper le casque », sans un mot
  // sur le flux qui ne répond pas.
  await seConnecter(page, "animateur");
  await casque(page).click();
  await expect(casque(page)).toHaveAccessibleName(/ne répond pas|injoignable|indisponible/, { timeout: 10_000 });
});

test("l’admin choisit la source de son casque, et la retrouve", async ({ page }) => {
  await seConnecter(page, "admin");
  const source = barre(page).getByRole("button", { name: /^Source du casque/ });
  await expect(source).toHaveAccessibleName("Source du casque : Antenne publique. Changer.");

  await source.click();
  await page.getByRole("menuitemradio", { name: /^Conducteur \(fichiers\)/ }).click();
  await expect(source).toHaveAccessibleName("Source du casque : Conducteur (fichiers). Changer.");
  await expect(casque(page)).toHaveAccessibleName("Écouter au casque : Conducteur (fichiers)");

  await page.reload();
  await expect(source).toHaveAccessibleName("Source du casque : Conducteur (fichiers). Changer.");
});

test("le menu du compte : qui est connecté, « Mon compte », puis la déconnexion", async ({ page }) => {
  await seConnecter(page, "programmateur");
  await barre(page).getByRole("button", { name: "Compte programmateur : menu" }).click();
  const menu = page.getByRole("menu", { name: "Compte programmateur : menu" });
  await expect(menu.getByText("programmateur", { exact: true })).toBeVisible();
  await expect(menu.getByText("Programmateur", { exact: true })).toBeVisible();

  await menu.getByRole("menuitem", { name: "Mon compte" }).click();
  await expect(page).toHaveURL(/\/reglages\?onglet=compte$/);
  await expect(page.getByRole("tabpanel", { name: "Mon compte" })).toBeVisible();

  await barre(page).getByRole("button", { name: "Compte programmateur : menu" }).click();
  await page.getByRole("menuitem", { name: "Se déconnecter" }).click();
  await expect(page.getByRole("button", { name: "Se connecter" })).toBeVisible();
  // La session est close chez le moteur aussi : recharger ne la rend pas.
  await page.reload();
  await expect(page.getByRole("button", { name: "Se connecter" })).toBeVisible();
});

test("le lien « Code source » ouvre les sources dans un nouvel onglet", async ({ page, context }) => {
  await seConnecter(page, "animateur");
  await barre(page).getByRole("button", { name: "Compte animateur : menu" }).click();
  const lien = page.getByRole("menuitem", { name: "Code source AGPL" });
  // L'adresse vient de la marque, sinon du dépôt de BUTTON.
  const marque = (await (await page.request.get("/brand.json")).json()) as { suite?: { sourceUrl?: string } };
  const adresse = marque.suite?.sourceUrl || DEFAULT_SOURCE_URL;
  await expect(lien).toHaveAttribute("href", adresse);

  const onglet = context.waitForEvent("page", { timeout: 5_000 });
  await lien.click();
  const sources = await onglet;
  await expect(sources).toHaveURL(adresse);
  // La console reste ouverte à côté.
  await expect(antenne(page)).toBeVisible();
  await sources.close();
});
