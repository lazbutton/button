import { devices, type Page } from "@playwright/test";
import type { AntenneIncident, AntenneState } from "../src/api/types.ts";
import { contraste, defautsGraves } from "./accessibilite.ts";
import { antenne, expect, seConnecter, test } from "./banc.ts";

// Chaque écran de la console passe axe-core, en clair, en sombre et sur un
// téléphone : un défaut grave ou critique fait échouer le parcours, avec la
// liste de ce qui ne va pas (accessibilite.ts). Les onglets se lisent dans la
// page : un onglet nouveau est vérifié sans rien changer ici. S'y ajoutent des
// états qu'un écran ne montre pas seul : des incidents ouverts, la barre latérale
// repliée, une tablette.

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

/** Deux incidents comme le relevé du moteur les donne. */
const INCIDENTS: AntenneIncident[] = [
  { kind: "icecast_down", detail: "radio.example:8000/live", since_s: 95, notified: true },
  { kind: "silence", detail: "−58 dB", since_s: 40, notified: false },
];

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
      // Survolée, une ligne prend le fond de survol : son heure, en gris pâle, reste lisible.
      const lignes = page.getByRole("list", { name: "Déroulé du conducteur" }).getByRole("listitem");
      await lignes.filter({ hasText: /\d:\d{2}/ }).last().hover();
      await verifier(page, "Conducteur, une ligne survolée");
      for (const [chemin, ecran] of [
        ["/programmation", "Programmation"],
        ["/sons", "Sons"],
        ["/reglages", "Réglages"],
      ] as const) {
        await page.goto(chemin);
        await verifierLesOnglets(page, ecran);
      }

      // Une confirmation : son bouton plein est rouge, comme dans chaque ConfirmDialog.
      await page.goto("/reglages?onglet=automate");
      await page.getByRole("button", { name: "Vider les files" }).click();
      const confirmation = page.getByRole("dialog", { name: "Vider les files ?" });
      await expect(confirmation).toBeVisible();
      await verifier(page, "Réglages, confirmation de « Vider les files »");
      await confirmation.getByRole("button", { name: "Annuler" }).click();
      await expect(confirmation).toBeHidden();

      await page.goto("/nulle-part");
      await expect(page.getByText("Page introuvable", { exact: true })).toBeVisible();
      await verifier(page, "page introuvable");
    });

    test("deux incidents ouverts : la barre du haut, son détail et l’antenne", async ({ page }) => {
      // Le moteur de démo n'a pas d'incident : son relevé en reçoit deux.
      await page.route("**/antenne/state.json", async (route) => {
        if (route.request().method() !== "GET") return route.continue();
        const reponse = await route.fetch();
        const releve = (await reponse.json()) as AntenneState;
        await route.fulfill({ response: reponse, json: { ...releve, incidents: INCIDENTS } });
      });
      await seConnecter(page, "admin");
      const etat = page.getByRole("banner").getByRole("button", { name: /, 2 incidents ouverts\.$/ });
      await expect(etat).toBeVisible();
      // Le badge du nombre est dessiné par le CSS : axe ne le voit pas, on le mesure.
      expect(await contraste(etat.locator("[data-count]")), "contraste du badge des incidents").toBeGreaterThanOrEqual(4.5);
      await verifier(page, "Antenne, deux incidents ouverts");

      await etat.click();
      const detail = page.getByRole("dialog", { name: "État de l’antenne" });
      await expect(detail.getByText("Incidents ouverts", { exact: true })).toBeVisible();
      await verifier(page, "Antenne, détail des incidents");
    });
  });
}

test("la barre latérale repliée, puis sur une tablette : la marque garde son nom", async ({ page }) => {
  await seConnecter(page, "admin");
  const laterale = page.getByRole("complementary", { name: "Navigation automate" });
  const marque = laterale.getByRole("link").first();
  const nom = ((await marque.textContent()) ?? "").trim();
  expect(nom, "nom de la station dans la barre latérale").not.toBe("");

  // Repliée, la barre ne montre plus que les icônes.
  await laterale.getByRole("button", { name: "Replier le menu" }).click();
  await expect(laterale.getByRole("button", { name: "Déplier le menu" })).toBeVisible();
  await expect(marque).toHaveAccessibleName(nom);
  await verifier(page, "barre latérale repliée");
  await laterale.getByRole("button", { name: "Déplier le menu" }).click();

  // Entre 721 et 1024 px, la barre ne montre que les icônes, même dépliée.
  await page.setViewportSize({ width: 900, height: 800 });
  await expect(laterale.getByRole("button", { name: "Replier le menu" })).toBeHidden();
  await expect(marque).toHaveAccessibleName(nom);
  await verifier(page, "tablette");
});

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
