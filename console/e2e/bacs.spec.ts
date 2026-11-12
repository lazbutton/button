import { devices, type Page, type Route } from "@playwright/test";
import type { CartsResponse, SkippedFile } from "../src/api/types.ts";
import { verifierAccessibilite } from "./accessibilite.ts";
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

/** Les réglages du bac ouvert, déjà ouverts sur un grand écran. */
async function reglagesDuBac(page: Page, titre: string) {
  const bouton = page.getByRole("region", { name: titre }).getByRole("button", { name: "Réglages du bac" });
  if ((await bouton.getAttribute("aria-pressed")) !== "true") await bouton.click();
  return page.getByRole("complementary", { name: "Réglages du bac" });
}

test("deux onglets modifient le même bac : le second est refusé, garde sa saisie, et rien n'est écrasé", async ({
  page,
}) => {
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons");

  await page.getByRole("complementary", { name: "Bacs" }).getByRole("button", { name: "Nouveau" }).click();
  const creation = page.getByRole("dialog", { name: "Nouveau bac" });
  await creation.getByLabel("Nom").fill("Bac à deux mains");
  await creation.getByRole("radio", { name: /^Fichiers/ }).click();
  await creation.getByRole("button", { name: "Créer le bac" }).click();
  await expect(creation).toBeHidden();
  await expect(page).toHaveURL(/[?&]id=\d+/);

  // Le second onglet ouvre le même bac, dans la même session.
  const autre = await page.context().newPage();
  await autre.goto(page.url());
  const premier = await reglagesDuBac(page, "Bac à deux mains");
  const second = await reglagesDuBac(autre, "Bac à deux mains");

  await premier.getByLabel("Notes").fill("Les notes du premier onglet");
  await premier.getByRole("button", { name: "Enregistrer" }).click();
  await expect(avis(page, "Bac enregistré")).toBeVisible();

  // Le second onglet montre encore le bac d'avant : il renvoie ses notes vides, avec sa version.
  await second.getByLabel("Nom", { exact: true }).fill("Bac à deux mains, renommé ");
  await second.getByRole("button", { name: "Enregistrer" }).click();
  await expect(alerte(autre, "Ce bac vient d'être modifié ailleurs : les notes.")).toBeVisible();
  await expect(avis(autre, "Bac enregistré")).toHaveCount(0);
  await expect(second.getByLabel("Nom", { exact: true })).toHaveValue("Bac à deux mains, renommé ");
  await expect(second.getByLabel("Notes")).toHaveValue("Les notes du premier onglet");
  await verifierAccessibilite(autre, "le refus d'un bac modifié ailleurs");

  // Revenu à ce qui est enregistré, plus rien à vérifier : le bandeau part, et ne revient pas avec la saisie suivante.
  await second.getByLabel("Nom", { exact: true }).fill("Bac à deux mains");
  await expect(second.getByText("Enregistré", { exact: true })).toBeVisible();
  await expect(alerte(autre, /modifié ailleurs/)).toHaveCount(0);
  await second.getByLabel("Nom", { exact: true }).fill("Bac à deux mains, renommé ");
  await expect(second.getByText("Modifié", { exact: true })).toBeVisible();
  await expect(alerte(autre, /modifié ailleurs/)).toHaveCount(0);

  await second.getByRole("button", { name: "Enregistrer" }).click();
  await expect(avis(autre, "Bac enregistré")).toBeVisible();
  await expect(alerte(autre, /modifié ailleurs/)).toHaveCount(0);
  // Le nom, comme le moteur l'a écrit : sans son espace, et plus rien à enregistrer.
  await expect(second.getByLabel("Nom", { exact: true })).toHaveValue("Bac à deux mains, renommé");
  await expect(second.getByText("Enregistré", { exact: true })).toBeVisible();
  await autre.close();

  // Relu dans le premier onglet : le nom du second, et les notes du premier.
  await page.reload();
  const relu = await reglagesDuBac(page, "Bac à deux mains, renommé");
  await expect(relu.getByLabel("Nom", { exact: true })).toHaveValue("Bac à deux mains, renommé");
  await expect(relu.getByLabel("Notes")).toHaveValue("Les notes du premier onglet");
});

test("un bac supprimé ailleurs pendant ses réglages : l'enregistrement le dit, en français", async ({ page }) => {
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons");

  await page.getByRole("complementary", { name: "Bacs" }).getByRole("button", { name: "Nouveau" }).click();
  const creation = page.getByRole("dialog", { name: "Nouveau bac" });
  await creation.getByLabel("Nom").fill("Bac éphémère");
  await creation.getByRole("radio", { name: /^Fichiers/ }).click();
  await creation.getByRole("button", { name: "Créer le bac" }).click();
  await expect(creation).toBeHidden();
  await expect(page).toHaveURL(/[?&]id=\d+/);

  const autre = await page.context().newPage();
  await autre.goto(page.url());
  const second = await reglagesDuBac(autre, "Bac éphémère");
  await second.getByLabel("Notes").fill("Des notes pour un bac parti");

  const premier = await reglagesDuBac(page, "Bac éphémère");
  await premier.getByRole("button", { name: "Supprimer" }).click();
  await page
    .getByRole("dialog", { name: "Supprimer « Bac éphémère » ?" })
    .getByRole("button", { name: "Supprimer le bac" })
    .click();
  await expect(avis(page, "« Bac éphémère » supprimé")).toBeVisible();

  await second.getByRole("button", { name: "Enregistrer" }).click();
  await expect(alerte(autre, "Ce bac n'existe plus : il a peut-être été supprimé.")).toBeVisible();
  await expect(autre.getByRole("option", { name: /Bac éphémère/ })).toHaveCount(0);
  await expect(autre).not.toHaveURL(/[?&]id=/);
  await autre.close();
});

test("des réglages fermés et rouverts avant la réponse : un message dit le refus, et nomme le bac", async ({
  page,
}) => {
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons");

  await page.getByRole("complementary", { name: "Bacs" }).getByRole("button", { name: "Nouveau" }).click();
  const creation = page.getByRole("dialog", { name: "Nouveau bac" });
  await creation.getByLabel("Nom").fill("Bac refermé");
  await creation.getByRole("radio", { name: /^Fichiers/ }).click();
  await creation.getByRole("button", { name: "Créer le bac" }).click();
  await expect(creation).toBeHidden();
  await expect(page).toHaveURL(/[?&]id=\d+/);

  const autre = await page.context().newPage();
  await autre.goto(page.url());
  const second = await reglagesDuBac(autre, "Bac refermé");
  await second.getByLabel("Notes").fill("Les notes du second onglet");

  const premier = await reglagesDuBac(page, "Bac refermé");
  await premier.getByLabel("Notes").fill("Les notes du premier onglet");
  await premier.getByRole("button", { name: "Enregistrer" }).click();
  await expect(avis(page, "Bac enregistré")).toBeVisible();

  // L'enregistrement du second onglet attend, le temps de fermer ses réglages et de les rouvrir.
  let lacher = () => {};
  const retenu = new Promise<void>((resolve) => {
    lacher = resolve;
  });
  await autre.route("**/carts/*.json", async (route) => {
    if (route.request().method() !== "PUT") return route.fallback();
    await retenu;
    return route.fallback();
  });
  await second.getByRole("button", { name: "Enregistrer" }).click();
  await second.getByRole("button", { name: "Fermer les réglages" }).click();
  const rouverts = await reglagesDuBac(autre, "Bac refermé");
  lacher();

  await expect(
    alerte(
      autre,
      "« Bac refermé » vient d'être modifié ailleurs : les notes. Tes changements n'y ont pas été enregistrés.",
    ),
  ).toBeVisible();
  await expect(rouverts.getByLabel("Notes")).toHaveValue("Les notes du premier onglet");
  await autre.close();
});

// Les réglages à côté du relais, comme sur un grand écran : les deux formulaires du bac à la fois.
test.describe("sur un grand écran", () => {
  test.use({ viewport: { width: 1700, height: 950 } });

  test("un relais relu pendant une saisie : rien d'enregistré ailleurs n'est écrasé", async ({ page }) => {
    await seConnecter(page, "programmateur");
    await expect(antenne(page)).toBeVisible();
    await page.goto("/sons");

    await page.getByRole("complementary", { name: "Bacs" }).getByRole("button", { name: "Nouveau" }).click();
    const creation = page.getByRole("dialog", { name: "Nouveau bac" });
    await creation.getByLabel("Nom").fill("Relais à deux mains");
    await creation.getByRole("radio", { name: /^Relais/ }).click();
    await creation.getByLabel("Adresse du flux").fill("https://radio.example/direct.mp3");
    await creation.getByLabel("Durée maximale en minutes").fill("60");
    await creation.getByRole("button", { name: "Créer le bac" }).click();
    await expect(creation).toBeHidden();
    await expect(page).toHaveURL(/[?&]id=\d+/);

    // Le second onglet tape des notes, sans les enregistrer.
    const autre = await page.context().newPage();
    await autre.goto(page.url());
    const relais = autre.getByRole("region", { name: "Relais à deux mains" });
    const second = await reglagesDuBac(autre, "Relais à deux mains");
    await second.getByLabel("Notes").fill("Les notes du second onglet");

    const premier = await reglagesDuBac(page, "Relais à deux mains");
    await premier.getByLabel("Notes").fill("Les notes du premier onglet");
    await premier.getByRole("button", { name: "Enregistrer" }).click();
    await expect(avis(page, "Bac enregistré")).toBeVisible();

    // Le second enregistre l'adresse, collée avec des espaces : elle n'a pas changé ailleurs, elle passe.
    // La page relit le relais, avec les notes du premier onglet.
    await relais.getByLabel("Adresse du flux").fill("  https://radio.example/autre.mp3 ");
    await relais.getByRole("button", { name: "Enregistrer" }).click();
    await expect(avis(autre, "Bac enregistré")).toBeVisible();
    await expect(relais.getByLabel("Adresse du flux")).toHaveValue("https://radio.example/autre.mp3");
    await expect(relais.getByText("Enregistré", { exact: true })).toBeVisible();

    // Les notes tapées restent, avec la version d'où leur saisie est partie : les enregistrer est refusé.
    await expect(second.getByLabel("Notes")).toHaveValue("Les notes du second onglet");
    await second.getByRole("button", { name: "Enregistrer" }).click();
    await expect(alerte(autre, "Ce bac vient d'être modifié ailleurs : les notes.")).toBeVisible();
    await autre.close();

    await page.reload();
    const relu = await reglagesDuBac(page, "Relais à deux mains");
    await expect(relu.getByLabel("Notes")).toHaveValue("Les notes du premier onglet");
    await expect(
      page.getByRole("region", { name: "Relais à deux mains" }).getByLabel("Adresse du flux"),
    ).toHaveValue("https://radio.example/autre.mp3");
  });
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
    /Dans le dossier de la station, sous Bacs\/\d+-Musique-de-d-mo, remplace-les par des sons que l'automate lit, ou retire-les\./,
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
