import { devices, type Page } from "@playwright/test";
import { defautsGraves } from "./accessibilite.ts";
import { antenne, expect, seConnecter, test } from "./banc.ts";

// Chaque écran de la console passe axe-core, en clair, en sombre et sur un
// téléphone : un défaut grave ou critique fait échouer le parcours, avec la
// liste de ce qui ne va pas (accessibilite.ts). Les onglets se lisent dans la
// page : un onglet nouveau est vérifié sans rien changer ici.

/** Vérifie l'écran une fois chargé, sans arrêter le parcours : un échec montre tous les écrans en défaut. */
async function verifier(page: Page, ecran: string) {
  await expect(page.getByText("Chargement…")).toHaveCount(0);
  expect.soft(await defautsGraves(page), `défauts d’accessibilité graves ou critiques : ${ecran}`).toEqual([]);
}

/** Vérifie chacun des onglets de la page ouverte, ceux de sa première liste d'onglets. */
async function verifierLesOnglets(page: Page, ecran: string) {
  // Les onglets suivent le rôle : on les compte une fois le compte chargé, quand
  // la barre du haut le nomme.
  await expect(page.getByRole("banner").getByRole("button", { name: /, compte .+ : menu$/ })).toBeVisible();
  const onglets = page.getByRole("tablist").first().getByRole("tab");
  await expect(onglets.first()).toBeVisible();
  const nombre = await onglets.count();
  for (let rang = 0; rang < nombre; rang++) {
    const onglet = onglets.nth(rang);
    await onglet.click();
    await expect(onglet).toHaveAttribute("aria-selected", "true");
    await verifier(page, `${ecran}, onglet ${(await onglet.innerText()).replace(/\s+/g, " ")}`);
  }
}

for (const [theme, colorScheme] of [
  ["clair", "light"],
  ["sombre", "dark"],
] as const) {
  test.describe(`en ${theme}`, () => {
    test.use({ colorScheme });

    test("l’écran de connexion et la page d’un invité", async ({ page }) => {
      await page.goto("/");
      await expect(page.getByRole("button", { name: "Se connecter" })).toBeVisible();
      await verifier(page, "connexion");

      // Sans lien valable, la page d'un invité le dit.
      await page.goto("/invitation");
      await expect(page.getByRole("alert")).toBeVisible();
      await verifier(page, "invitation");
    });

    test("chaque page et chaque onglet de l’admin, avec ses menus et ses panneaux", async ({ page }) => {
      // Une quinzaine d'analyses : plus lent qu'un parcours ordinaire, surtout en CI.
      test.slow();
      await seConnecter(page, "admin");
      await expect(antenne(page).getByRole("button", { name: /^Suivant/ })).toBeEnabled();
      await verifier(page, "Antenne");

      const barre = page.getByRole("banner");
      await barre.getByRole("button", { name: /, compte .+ : menu$/ }).click();
      await expect(page.getByRole("menu")).toBeVisible();
      await verifier(page, "Antenne, menu du compte");
      await page.keyboard.press("Escape");

      await barre.getByRole("button", { name: /^Antenne : / }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await verifier(page, "Antenne, état de l’antenne");
      await page.keyboard.press("Escape");

      await antenne(page).getByRole("button", { name: "Passer en direct" }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await verifier(page, "Antenne, panneau du direct");
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toBeHidden();

      // Chaque page s'ouvre par son adresse : rien ne reste de la précédente.
      await page.goto("/conducteur");
      await expect(page.getByRole("main")).toBeVisible();
      await verifier(page, "Conducteur");
      for (const [chemin, ecran] of [
        ["/programmation", "Programmation"],
        ["/sons", "Sons"],
        ["/reglages", "Réglages"],
      ] as const) {
        await page.goto(chemin);
        await verifierLesOnglets(page, ecran);
      }

      await page.goto("/nulle-part");
      await expect(page.getByText("Page introuvable", { exact: true })).toBeVisible();
      await verifier(page, "page introuvable");
    });
  });
}

// Le téléphone de telephone.spec.ts, dans un groupe : Playwright n'y accepte pas
// le choix du navigateur, déjà Chromium.
const { defaultBrowserType: _chromium, ...telephone } = devices["Pixel 9"];

test.describe("sur un téléphone", () => {
  test.use(telephone);

  test("les pages de l’animateur, et le menu de navigation", async ({ page }) => {
    await seConnecter(page, "animateur");
    await expect(antenne(page)).toBeVisible();
    await verifier(page, "Antenne");

    await page.getByRole("button", { name: "Ouvrir la navigation" }).tap();
    const menu = page.getByRole("dialog", { name: "Navigation" });
    await expect(menu).toBeVisible();
    await verifier(page, "menu de navigation");

    await menu.getByRole("link", { name: "Conducteur" }).tap();
    await expect(menu).toBeHidden();
    await expect(page.getByRole("main")).toBeVisible();
    await verifier(page, "Conducteur");

    await page.goto("/reglages");
    await verifierLesOnglets(page, "Réglages");

    // Programmation est réservée aux programmateurs : l'écran le dit.
    await page.goto("/programmation");
    await expect(page.getByText("Accès réservé", { exact: true })).toBeVisible();
    await verifier(page, "accès réservé");
  });
});
