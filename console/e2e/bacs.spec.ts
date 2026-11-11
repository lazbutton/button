import { devices, type Page, type Route } from "@playwright/test";
import type { CartsResponse, SkippedFile } from "../src/api/types.ts";
import { alerte, antenne, avis, expect, seConnecter, test } from "./banc.ts";

// La page des bacs, avec le compte qui les prépare : le programmateur. Un bac
// créé ici reste dans le moteur de démo jusqu'à la fin du lancement.

// Le moteur de démo n'a pas de scheduler pour relever le dossier d'un bac : les
// fichiers qu'il n'a pas pris sont simulés par page.route, comme le moteur les
// rend.
const CARTS = "**/carts.json";
const REFUS: SkippedFile[] = [
  { path: "faux.mp3", reason: "ce n'est pas un fichier audio" },
  { path: "Chronique du 4 novembre.ogg", reason: "durée illisible" },
  { path: "verrouillé.wav", reason: "lecture impossible" },
  { path: "Brouillon/Montage final.m4a", reason: "durée illisible" },
  { path: "notes.mp3", reason: "ce n'est pas un fichier audio" },
  { path: "Interview.mp3", reason: "ce n'est pas un fichier audio" },
];

/** Les bacs du moteur, avec leurs fichiers refusés par titre ; `null` : un moteur plus ancien, qui ne les donne pas. */
function avecDesRefus(refus: Record<string, SkippedFile[] | null>): (route: Route) => Promise<void> {
  return async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const reponse = await route.fetch();
    const corps = (await reponse.json()) as CartsResponse;
    corps.carts = corps.carts.map((cart) => {
      const liste = refus[cart.title];
      if (liste === undefined) return cart;
      const { skipped_files: _rendus, ...bac } = cart;
      return liste === null ? bac : { ...bac, skipped_files: liste };
    });
    await route.fulfill({ response: reponse, json: corps });
  };
}

async function ouvrirLeBac(page: Page, titre: string) {
  await page.getByRole("option", { name: new RegExp(titre) }).click();
  return page.getByRole("region", { name: titre });
}

test("« Diffuser maintenant » sur un bac sans son prêt dit que rien n'est parti", async ({ page }) => {
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons");

  await page.getByRole("complementary", { name: "Bacs" }).getByRole("button", { name: "Nouveau" }).click();
  const creation = page.getByRole("dialog", { name: "Nouveau bac" });
  await creation.getByLabel("Nom").fill("Bac sans son");
  await creation.getByRole("radio", { name: /^Fichiers/ }).click();
  await creation.getByRole("button", { name: "Créer le bac" }).click();
  await expect(creation).toBeHidden();

  await page.getByRole("region", { name: "Bac sans son" }).getByRole("button", { name: "Diffuser maintenant" }).click();
  await expect(alerte(page, "Ce bac n'a aucun son prêt : rien n'est parti à l'antenne.")).toBeVisible();
  await expect(avis(page, /envoyé à l'antenne/)).toHaveCount(0);
});

test("les réglages d'un bac donnent le nom de son dossier, à copier pour Dropbox", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons");

  await page.getByRole("complementary", { name: "Bacs" }).getByRole("button", { name: "Nouveau" }).click();
  const creation = page.getByRole("dialog", { name: "Nouveau bac" });
  await creation.getByLabel("Nom").fill("Bac Dropbox été");
  await creation.getByRole("radio", { name: /^Fichiers/ }).click();
  await creation.getByRole("button", { name: "Créer le bac" }).click();
  await expect(creation).toBeHidden();

  // Sur un grand écran, les réglages sont déjà ouverts.
  const bouton = page.getByRole("region", { name: "Bac Dropbox été" }).getByRole("button", { name: "Réglages du bac" });
  if ((await bouton.getAttribute("aria-pressed")) !== "true") await bouton.click();
  const reglages = page.getByRole("complementary", { name: "Réglages du bac" });
  await reglages.getByText("Avancé", { exact: true }).click();

  // Le titre devient le nom du dossier comme chez le moteur : « été » y devient « -t ».
  const chemin = reglages.getByText(/^Bacs\/\d+-Bac-Dropbox-t$/);
  await expect(chemin).toBeVisible();
  const nom = (await chemin.textContent())?.replace(/^Bacs\//, "");
  await reglages.getByRole("button", { name: "Copier le nom" }).click();
  await expect(reglages.getByRole("button", { name: "Copié" })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(nom);
});

test("au-dessus de ses sons, un bac dit les fichiers de son dossier qu'il n'a pas pris", async ({ page }) => {
  await page.route(CARTS, avecDesRefus({ "Musique de démo": REFUS, Jingles: null }));
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons");

  const bac = await ouvrirLeBac(page, "Musique de démo");
  const refus = bac.getByRole("region", { name: "6 fichiers ne sont pas entrés dans le bac" });
  await expect(refus.getByRole("listitem")).toHaveText([
    "faux.mp3 ce n'est pas un fichier audio",
    "Chronique du 4 novembre.ogg durée illisible",
    "verrouillé.wav lecture impossible",
  ]);
  await expect(refus).toContainText(
    /Remplace-les dans Bacs\/\d+-Musique-de-d-mo par des sons que l'automate lit, ou retire-les\./,
  );
  // Entre l'en-tête du bac et la liste de ses sons.
  const encart = await refus.boundingBox();
  const sons = await bac.getByRole("toolbar", { name: "Sons du bac" }).boundingBox();
  expect(encart && sons && encart.y + encart.height).toBeLessThanOrEqual((sons?.y ?? 0) + 1);

  // Au clavier, la suite s'ouvre.
  await refus.getByText("Voir les 3 autres").focus();
  await page.keyboard.press("Enter");
  await expect(refus.getByRole("listitem")).toHaveCount(REFUS.length);
  await expect(refus.getByRole("listitem").last()).toHaveText("Interview.mp3 ce n'est pas un fichier audio");

  // Un moteur plus ancien ne donne pas la liste : rien ne s'affiche.
  const jingles = await ouvrirLeBac(page, "Jingles");
  await expect(jingles.getByRole("toolbar", { name: "Sons du bac" })).toBeVisible();
  await expect(jingles.getByRole("region", { name: /dans le bac|trop de fichiers/ })).toHaveCount(0);
});

test.describe("en sombre", () => {
  test.use({ colorScheme: "dark" });

  // Le parcours finit par l'analyse d'axe, contrastes compris, en sombre.
  test("les fichiers refusés se lisent en sombre, comme le dossier entier au-delà de 2000 sons", async ({ page }) => {
    const dossier = { path: ".", reason: "plus de 2000 fichiers audio : le bac ne prend plus rien de son dossier" };
    await page.route(CARTS, avecDesRefus({ "Musique de démo": [dossier] }));
    await seConnecter(page, "programmateur");
    await expect(antenne(page)).toBeVisible();
    await page.goto("/sons");

    const bac = await ouvrirLeBac(page, "Musique de démo");
    const refus = bac.getByRole("region", { name: "Le dossier du bac a trop de fichiers" });
    await expect(refus.getByRole("listitem")).toHaveText([
      /^Bacs\/\d+-Musique-de-d-mo plus de 2000 fichiers audio : le bac ne prend plus rien de son dossier$/,
    ]);
  });
});

test.describe("sur un téléphone", () => {
  const { defaultBrowserType: _navigateur, ...telephone } = devices["Pixel 9"];
  test.use(telephone);

  test("40 fichiers refusés, dépliés, laissent la liste des sons à l'écran", async ({ page }) => {
    const nombreux = Array.from({ length: 40 }, (_, index) => ({
      path: `Message vocal ${String(index + 1).padStart(2, "0")}.mp3`,
      reason: "ce n'est pas un fichier audio",
    }));
    await page.route(CARTS, avecDesRefus({ "Musique de démo": nombreux }));
    await seConnecter(page, "programmateur");
    await expect(antenne(page)).toBeVisible();
    await page.goto("/sons");

    const bac = await ouvrirLeBac(page, "Musique de démo");
    const refus = bac.getByRole("region", { name: "40 fichiers ne sont pas entrés dans le bac" });
    const suite = refus.getByText("Voir les 37 autres");
    // Une cible pour le doigt : 40 px de haut au moins.
    expect((await suite.boundingBox())?.height).toBeGreaterThanOrEqual(40);
    await suite.click();
    await expect(refus.getByRole("listitem")).toHaveCount(40);

    await expect(bac.getByRole("button", { name: "Pré-écouter Première écoute" })).toBeInViewport({ ratio: 1 });
    const largeur = await page.evaluate(() => ({
      page: document.documentElement.scrollWidth,
      ecran: document.documentElement.clientWidth,
    }));
    expect(largeur.page, "défilement de côté").toBeLessThanOrEqual(largeur.ecran);
  });
});
