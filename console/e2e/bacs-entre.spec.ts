import type { Page, Route } from "@playwright/test";
import { antenne, avis, expect, seConnecter, test } from "./banc.ts";

// Classer, déplacer et copier entre les bacs (FON-70), derrière l'interrupteur
// général de « Ranger la banque ». Le moteur du banc le garde éteint : le
// parcours l'allume dans /account.json, et répond lui-même aux deux gestes
// qui écrivent, d'après les bacs du banc (engine/tests/e2e/seed.py).

type Bac = { id: number; title: string; sounds: Array<{ id: number; rank: number; title: string }> };

async function allumer(page: Page) {
  await page.route("**/account.json", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const reponse = await route.fetch();
    const compte = (await reponse.json()) as Record<string, unknown>;
    await route.fulfill({ response: reponse, json: { ...compte, features: { bank_tidy: true } } });
  });
}

async function bacs(page: Page): Promise<Bac[]> {
  return ((await (await page.request.get("/carts.json")).json()) as { carts: Bac[] }).carts;
}

async function ouvrir(page: Page, titre: string) {
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons");
  await page.getByRole("option", { name: new RegExp(titre) }).click();
  return page.getByRole("region", { name: titre });
}

test("trier la vue d'un bac sans changer son ordre, puis l'appliquer", async ({ page }) => {
  await allumer(page);
  const recus: Array<Record<string, unknown>> = [];
  await page.route("**/carts/*/sounds/ranks.json", async (route: Route) => {
    const corps = route.request().postDataJSON() as { ranks: number[] };
    recus.push(corps);
    const bac = (await bacs(page)).find((item) => item.title === "Musique de démo") as Bac;
    const sons = corps.ranks.map((id, rang) => ({ ...bac.sounds.find((son) => son.id === id), rank: rang + 1 }));
    await route.fulfill({ json: { cart: { ...bac, sounds: sons } } });
  });
  const bac = await ouvrir(page, "Musique de démo");
  const lignes = bac.locator("tbody tr");
  await expect(lignes.first()).toContainText("Première écoute");

  await bac.getByRole("combobox", { name: "Trier la vue" }).click();
  await page.getByRole("option", { name: "Par titre" }).click();
  await expect(bac.getByRole("status").filter({ hasText: "le bac passe toujours dans son ordre" })).toBeVisible();
  await expect(lignes.first()).toContainText("Nuit claire");
  // Les rangs du bac restent ceux de son ordre de passage.
  await expect(lignes.first().locator(".c-rank")).toHaveText(/2/);
  expect(recus).toEqual([]);

  await bac.getByRole("button", { name: "Appliquer cet ordre au bac" }).click();
  await expect(avis(page, "« Musique de démo » passe maintenant dans cet ordre.")).toBeVisible();
  const ordre = (recus[0].ranks as number[]).length;
  expect(ordre).toBe(3);
  expect(recus[0].sorted_by).toBe("title");
  await expect(bac.getByRole("status").filter({ hasText: "Vue triée" })).toHaveCount(0);
});

test("copier deux sons dans un autre bac", async ({ page }) => {
  await allumer(page);
  const recus: Array<Record<string, unknown>> = [];
  await page.route("**/carts/*/sounds/transfer.json", async (route: Route) => {
    const corps = route.request().postDataJSON() as { ids: number[]; to: number; copy: boolean };
    recus.push(corps);
    const tous = await bacs(page);
    const source = tous.find((item) => item.title === "Musique de démo") as Bac;
    const cible = tous.find((item) => item.id === corps.to) as Bac;
    const copies = source.sounds.filter((son) => corps.ids.includes(son.id));
    await route.fulfill({
      json: { cart: source, target: { ...cible, sounds: [...cible.sounds, ...copies] }, done: copies.length, skipped: [] },
    });
  });
  const bac = await ouvrir(page, "Musique de démo");
  await bac.getByRole("checkbox", { name: /Première écoute/ }).click();
  await bac.getByRole("checkbox", { name: /Nuit claire/ }).click();
  await bac.getByRole("toolbar", { name: "Sélection" }).getByRole("button", { name: "Copier dans un bac" }).click();

  const fenetre = page.getByRole("dialog", { name: "Copier ces 2 sons dans un bac" });
  await fenetre.getByRole("combobox", { name: "Bac" }).click();
  await page.getByRole("option", { name: "Pubs" }).click();
  await fenetre.getByRole("button", { name: "Copier dans « Pubs »" }).click();
  await expect(avis(page, "2 sons copiés dans « Pubs ».")).toBeVisible();
  expect(recus).toHaveLength(1);
  expect(recus[0].copy).toBe(true);
  expect((recus[0].ids as number[]).length).toBe(2);
});
