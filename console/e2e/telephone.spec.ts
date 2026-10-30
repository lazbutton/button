import { devices, type Locator } from "@playwright/test";
import { antenne, bibliotheque, expect, file, seConnecter, test } from "./banc.ts";

// La console à la largeur d'un téléphone, 360 px, au doigt : rien ne déborde,
// le pupitre s'empile, la navigation passe par un menu, les gestes marchent.
test.use({ ...devices["Pixel 9"] });

test.beforeEach(async ({ page }) => {
  await seConnecter(page, "animateur");
  await expect(file(page).getByRole("listitem").first()).toBeVisible();
});

/** La place d'un élément affiché, en px. */
async function boite(element: Locator) {
  const mesure = await element.boundingBox();
  if (!mesure) throw new Error(`${element} n’est pas affiché.`);
  return mesure;
}

/** Les cibles trop petites pour un doigt : 40 px de côté au moins, dit console/AGENTS.md. */
async function cibles(elements: Locator[]): Promise<string[]> {
  const petites: string[] = [];
  for (const element of elements) {
    const { width, height } = await boite(element);
    if (width < 40 || height < 40) petites.push(`${element} : ${Math.round(width)} × ${Math.round(height)} px`);
  }
  return petites;
}

test("rien ne déborde, et le pupitre s’empile : l’antenne, la file, puis la bibliothèque", async ({ page }) => {
  const largeur = await page.evaluate(() => ({
    page: document.documentElement.scrollWidth,
    ecran: document.documentElement.clientWidth,
  }));
  expect(largeur.page, "défilement de côté").toBeLessThanOrEqual(largeur.ecran);

  const [carte, suite, biblio] = await Promise.all([antenne(page), file(page), bibliotheque(page)].map(boite));
  expect(suite.y).toBeGreaterThanOrEqual(carte.y + carte.height);
  expect(biblio.y).toBeGreaterThanOrEqual(suite.y + suite.height);
  for (const region of [carte, suite, biblio]) expect(region.width).toBeLessThanOrEqual(largeur.ecran);
});

test("la navigation passe par un menu", async ({ page }) => {
  // La colonne de navigation du bureau est cachée.
  await expect(page.getByRole("navigation", { name: "Console" })).toBeHidden();

  await page.getByRole("button", { name: "Ouvrir la navigation" }).tap();
  const menu = page.getByRole("dialog", { name: "Navigation" });
  await expect(menu.getByRole("navigation", { name: "Console" }).getByRole("link")).toHaveText([
    "Antenne",
    "Conducteur",
    "Réglages",
  ]);
  await menu.getByRole("link", { name: "Conducteur" }).tap();
  await expect(page).toHaveURL(/\/conducteur$/);
  await expect(menu).toBeHidden();

  await page.getByRole("button", { name: "Ouvrir la navigation" }).tap();
  await menu.getByRole("link", { name: "Antenne" }).tap();
  await expect(page).toHaveURL(/\/antenne$/);
  await expect(antenne(page)).toBeVisible();
});

test("les gestes du pupitre se font au doigt", async ({ page }) => {
  await bibliotheque(page).getByRole("button", { name: "Diffuser Jingle station maintenant" }).tap();
  await expect(antenne(page).getByText("Jingle station", { exact: true })).toBeVisible();

  const direct = antenne(page).getByRole("button", { name: "Passer en direct" });
  await direct.tap();
  const panneau = page.getByRole("dialog");
  await expect(panneau).toBeVisible();
  await panneau.getByRole("button", { name: "Fermer" }).tap();
  await expect(panneau).toBeHidden();
  await expect(direct).toBeFocused();

  const casque = page.getByRole("banner").getByRole("button", { name: /^(Écouter au casque|Arrêter l’écoute)/ });
  await casque.tap();
  await expect(casque).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("banner").getByRole("button", { name: "Compte animateur : menu" }).tap();
  await expect(page.getByRole("menuitem", { name: "Code source AGPL" })).toBeVisible();
});

test("les cibles du pupitre et de la barre font 40 px au moins", async ({ page }) => {
  const barre = page.getByRole("banner");
  const ligne = file(page).getByRole("listitem").first();
  const resultat = bibliotheque(page).getByRole("listitem").first();
  const petites = await cibles([
    page.getByRole("button", { name: "Ouvrir la navigation" }),
    barre.getByRole("button", { name: /^Antenne : / }),
    barre.getByRole("button", { name: /^Écouter au casque/ }),
    barre.getByRole("button", { name: /^Compte / }),
    antenne(page).getByRole("button", { name: /^Suivant/ }),
    antenne(page).getByRole("button", { name: "Passer en direct" }),
    ligne.getByRole("button", { name: /^Retirer / }),
    bibliotheque(page).getByRole("searchbox"),
    ...(await bibliotheque(page).getByRole("tab").all()),
    resultat.getByRole("button", { name: /^Mettre / }),
    resultat.getByRole("button", { name: /^Pré-écouter / }),
    resultat.getByRole("button", { name: /^Diffuser / }),
  ]);
  expect(petites).toEqual([]);
});

test("la poignée pour déplacer une ligne de la file fait 40 px au moins", async ({ page }) => {
  const petites = await cibles([file(page).getByRole("listitem").first().getByRole("button", { name: /^Déplacer / })]);
  expect(petites).toEqual([]);
});
