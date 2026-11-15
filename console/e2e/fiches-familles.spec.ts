import type { Page, Route } from "@playwright/test";
import { antenne, expect, seConnecter, test } from "./banc.ts";

// Les familles, le verdict et les sélections de titres (FON-28). Le moteur du banc
// n'a ni bibliothèque Beets, ni le rangement allumé : le parcours allume
// l'interrupteur dans /account.json, et tient ici les routes des fiches, comme le
// moteur (engine/radiotomate/services/fiches_families.py).

async function rangementOuvert(page: Page) {
  await page.route("**/account.json", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const reponse = await route.fetch();
    const corps = (await reponse.json()) as Record<string, unknown>;
    await route.fulfill({ response: reponse, json: { ...corps, features: { bank_tidy: true, title_edits: true } } });
  });
}

test("sous les sélections, les familles disent où tombent leurs titres", async ({ page }) => {
  await rangementOuvert(page);
  await page.route("**/fiches/familles.json", async (route: Route) => {
    await route.fulfill({
      json: {
        library: 4,
        verdict: true,
        selections: [],
        families: [
          {
            value: "jazz",
            label: "Jazz",
            count: 2,
            uncategorized: 0,
            selections: [{ id: 1, name: "Jazz du soir", count: 2 }],
            sample: [],
          },
          {
            value: "",
            label: "",
            count: 2,
            uncategorized: 2,
            selections: [],
            sample: [
              { id: 3, title: "Comète", artist: "Orage" },
              { id: 4, title: "Brume", artist: "Orage" },
            ],
          },
        ],
      },
    });
  });
  await page.route("**/fiches/reglages.json", (route: Route) =>
    route.fulfill({
      json: {
        enabled: true,
        verdict: true,
        acoustid_key_set: false,
        sources: { tidal: false, apple_music: false, bandcamp: false, tidal_key_set: false },
        sent: "",
      },
    }),
  );
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/programmation?onglet=categories");

  // Replié d'abord : il joue toutes les sélections sur la bibliothèque.
  const familles = page.getByRole("region", { name: "Familles et sélections" });
  const voir = familles.getByRole("button", { name: "Voir les familles" });
  await expect(voir).toHaveAttribute("aria-expanded", "false");
  await voir.click();
  await expect(familles.getByRole("row", { name: /Jazz 2 Jazz du soir · 2 0/ })).toBeVisible();
  const sans = familles.getByRole("button", { name: "2 titres de Sans famille sans sélection" });
  await sans.click();
  await expect(sans).toHaveAttribute("aria-expanded", "true");
  await expect(familles.getByText("Orage – Comète")).toBeVisible();

  // L'aide de la requête dit la famille, et le verdict, allumé.
  await page.getByRole("button", { name: "Nouvelle sélection" }).click();
  const fenetre = page.getByRole("dialog");
  const main = fenetre.getByRole("radio", { name: "Écrire la requête à la main" });
  if (await main.count()) await main.click();
  await expect(fenetre.getByText("Exemples : grouping:matinale · genres:Jazz · famille:jazz · fmg:oui")).toBeVisible();
});

test("effacer les verdicts nomme d'abord la sélection qui se videra", async ({ page }) => {
  await rangementOuvert(page);
  await page.route("**/fiches/reglages.json", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: {
        enabled: true,
        verdict: true,
        acoustid_key_set: false,
        sources: { tidal: false, apple_music: false, bandcamp: false, tidal_key_set: false },
        sent: "l'artiste et le titre.",
      },
    });
  });
  const resume = { titles: 2, waiting: 1, selections: [{ id: 5, name: "Femmes", query: "fmg:oui", count: 12 }] };
  await page.route("**/fiches/verdicts.json", (route: Route) => route.fulfill({ json: resume }));
  let effaces = 0;
  await page.route("**/fiches/verdicts/effacer.json", async (route: Route) => {
    effaces += 1;
    await route.fulfill({ json: resume });
  });
  await seConnecter(page, "admin");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/reglages?onglet=fiches");

  const carte = page.getByRole("region", { name: "Effacer les verdicts" });
  await carte.getByRole("button", { name: "Effacer les verdicts…" }).click();
  const fenetre = page.getByRole("alertdialog").or(page.getByRole("dialog"));
  await expect(fenetre.getByText(/La sélection « Femmes » \(12 titres\) lit le verdict : elle se videra\./)).toBeVisible();
  expect(effaces).toBe(0);
  await fenetre.getByRole("button", { name: "Effacer les verdicts" }).click();
  await expect(carte.getByRole("status")).toHaveText("Verdicts effacés de 2 titres.");
  expect(effaces).toBe(1);
});
