import type { Page, Route } from "@playwright/test";
import { CONDUCTEUR_JSON } from "../src/api/rundownLive.ts";
import type { Rundown, RundownItem } from "../src/api/types.ts";
import { alerte, antenne, avis, expect, seConnecter, test } from "./banc.ts";

// La page Conducteur : ce qui va passer, lu dans les mots de la console, les
// lignes à réparer, un retrait, et un conducteur qui ne répond plus. Une ligne
// sans son et un retrait sont simulés par page.route devant le moteur de démo :
// son horloge trouve toujours ses sons, et un retrait ne change pas le moteur
// que les autres parcours partagent.

const CONDUCTEUR = "**/autodj/conducteur.json*";
const LIGNE = "**/autodj/conducteur/items/*.json";
const deroule = (page: Page) => page.getByRole("list", { name: "Déroulé du conducteur" });
const lignes = (page: Page) => deroule(page).getByRole("listitem");
const retraits = (page: Page) => page.getByRole("button", { name: /^Retirer .+ du conducteur$/ });

async function ouvrir(page: Page, role: "animateur" | "programmateur"): Promise<void> {
  await seConnecter(page, role);
  // La session ouverte, et pas avant : partir plus tôt couperait la connexion.
  await expect(antenne(page)).toBeVisible();
  await page.goto("/conducteur");
  await expect(lignes(page).first()).toBeVisible();
}

/**
 * Le conducteur du moteur, où une ligne de l'horloge à venir n'a plus de son :
 * son bac est introuvable. La même ligne d'une lecture à l'autre, choisie à la
 * première.
 */
function avecUnBacVide(): (route: Route) => Promise<void> {
  let choisie: string | undefined;
  return async (route) => {
    const reponse = await route.fetch();
    const conducteur = (await reponse.json()) as Rundown;
    const apres = Date.now() + 60_000;
    choisie ??= conducteur.items.find((item) => item.origin === "clock" && Date.parse(item.at) > apres)?.id;
    conducteur.items = conducteur.items.map((item): RundownItem => {
      if (!choisie || item.id !== choisie) return item;
      const { title: _title, artist: _artist, category: _category, ...ligne } = item;
      return {
        ...ligne,
        kind: "jingle",
        status: "manquant",
        status_code: "failed",
        reason: "cart introuvable",
        resource: "Bac fantôme",
        cart: "Bac fantôme",
      };
    });
    await route.fulfill({ response: reponse, json: conducteur });
  };
}

test("le conducteur se lit dans les mots de la console", async ({ page }) => {
  await ouvrir(page, "animateur");
  const conducteur = page.getByRole("main");
  await expect(conducteur.getByText("Heure type", { exact: true })).toBeVisible();
  await expect(conducteur.getByText("Horloge des parcours", { exact: true })).toBeVisible();
  // Une ligne à l'antenne ; « prévu » et « séquentiel » ne se disent plus sur chaque ligne.
  await expect(lignes(page).filter({ hasText: "À l’antenne" })).toHaveCount(1);
  await expect(deroule(page)).not.toContainText("prévu");
  await expect(deroule(page)).not.toContainText("séquentiel");
  // L'animateur lit le conducteur sans le changer.
  await expect(retraits(page)).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Horloge des parcours" })).toHaveCount(0);
});

test("une ligne sans son : le bandeau la compte, et mène à son bouton « Réparer »", async ({ page }) => {
  await page.route(CONDUCTEUR, avecUnBacVide());
  await ouvrir(page, "programmateur");
  await expect(page.getByText(/^1 ligne à réparer d’ici \d{2}:\d{2}\.$/)).toBeVisible();

  await page.getByRole("button", { name: "Voir la ligne" }).click();
  const reparer = page.getByRole("button", { name: "Réparer Bac fantôme" });
  await expect(reparer).toBeFocused();
  await expect(lignes(page).filter({ has: reparer })).toContainText("bac introuvable ou sans son");

  await page.keyboard.press("Enter");
  const dialogue = page.getByRole("dialog", { name: "Réparer « Bac fantôme »" });
  await expect(dialogue).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialogue).toBeHidden();
  // Fermé, le dialogue rend le focus au bouton qui l'a ouvert.
  await expect(reparer).toBeFocused();
});

test("l’animateur voit la ligne à réparer, et qui peut la réparer", async ({ page }) => {
  await page.route(CONDUCTEUR, avecUnBacVide());
  await ouvrir(page, "animateur");
  await expect(page.getByText("Un programmateur peut la réparer ici.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Réparer / })).toHaveCount(0);

  await page.getByRole("button", { name: "Voir la ligne" }).click();
  await expect(lignes(page).filter({ hasText: "Bac fantôme" })).toBeFocused();
});

test("retirer une ligne au clavier : elle quitte le déroulé, et le focus reste dans la page", async ({ page }) => {
  // Le retrait ne va pas jusqu'au moteur : la page répond comme lui, sans la ligne.
  const retirees = new Set<string>();
  const sansLesRetirees = (conducteur: Rundown): Rundown => ({
    ...conducteur,
    items: conducteur.items.filter((item) => !item.id || !retirees.has(item.id)),
  });
  await page.route(CONDUCTEUR, async (route) => {
    const reponse = await route.fetch();
    await route.fulfill({ response: reponse, json: sansLesRetirees((await reponse.json()) as Rundown) });
  });
  await page.route(LIGNE, async (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    const nom = new URL(route.request().url()).pathname.split("/").pop() ?? "";
    retirees.add(decodeURIComponent(nom.replace(/\.json$/, "")));
    const reponse = await route.fetch({ method: "GET", url: new URL(CONDUCTEUR_JSON, route.request().url()).toString() });
    await route.fulfill({ response: reponse, json: sansLesRetirees((await reponse.json()) as Rundown) });
  });
  await ouvrir(page, "programmateur");

  const ligne = lignes(page).filter({ has: retraits(page) }).first();
  const heure = await ligne.locator("time").getAttribute("datetime");
  await ligne.getByRole("button", { name: /^Retirer / }).focus();
  await page.keyboard.press("Enter");

  await expect(avis(page, "Retiré du conducteur.")).toBeVisible();
  await expect(deroule(page).locator(`time[datetime="${heure}"]`)).toHaveCount(0);
  // Sa ligne partie, le bouton aussi : le focus revient au déroulé.
  await expect(deroule(page)).toBeFocused();
});

test("un retrait sans réponse le dit en alerte, et la ligne reste", async ({ page }) => {
  await page.route(LIGNE, (route) =>
    route.request().method() === "DELETE" ? route.abort("connectionrefused") : route.fallback(),
  );
  await ouvrir(page, "programmateur");

  const ligne = lignes(page).filter({ has: retraits(page) }).first();
  const heure = await ligne.locator("time").getAttribute("datetime");
  await ligne.getByRole("button", { name: /^Retirer / }).click();

  await expect(alerte(page, "L’automate ne répond pas. Réessaie dans un instant.")).toBeVisible();
  await expect(deroule(page).locator(`time[datetime="${heure}"]`)).toHaveCount(1);
});

test("un conducteur qui ne répond plus le dit, et garde ses lignes", async ({ page }) => {
  await ouvrir(page, "animateur");
  const vieilli = "Le conducteur ne répond plus : ces lignes peuvent avoir changé.";
  await page.route(CONDUCTEUR, (route) => route.abort("connectionrefused"));

  await expect(avis(page, vieilli)).toBeVisible({ timeout: 10_000 });
  await expect(lignes(page).first()).toBeVisible();

  // Le conducteur revient de lui-même avec le moteur.
  await page.unroute(CONDUCTEUR);
  await expect(avis(page, vieilli)).toHaveCount(0, { timeout: 10_000 });
});
