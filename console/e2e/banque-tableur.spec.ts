import type { Page, Route } from "@playwright/test";
import { antenne, avis, expect, seConnecter, test } from "./banc.ts";

// Corriger comme dans un tableur (FON-67). Comme pour la fiche (banque-fiche.spec.ts),
// le parcours allume le rangement et la correction dans /account.json, et tient
// ici une bibliothèque de 30 titres sans album, que les routes du tableau et de
// l'écriture lisent et changent comme le moteur.

type Champ = "title" | "artist" | "album" | "year" | "genre" | "famille";
type Titre = {
  id: number;
  title: string;
  artist: string;
  album: string;
  year: number | null;
  genre: string;
  famille: string;
  famille_label: string;
  duration: number;
  zone: string;
  collection: string;
  path: string;
  missing: string[];
};
type Lot = { titles: Array<{ id: number; values: Partial<Record<Champ, string>> }>; dry_run?: boolean };

function bibliotheque(): Titre[] {
  return Array.from({ length: 30 }, (_, index) => {
    const id = index + 1;
    return {
      id,
      title: `Titre ${String(id).padStart(2, "0")}`,
      artist: "Orage",
      album: "",
      year: 2015,
      genre: "Jazz",
      famille: "jazz",
      famille_label: "Jazz",
      duration: 180,
      zone: "rotation",
      collection: "rotation",
      path: `10-rotation/${id}.mp3`,
      missing: ["album"],
    };
  });
}

async function tableur(page: Page): Promise<{ lots: Lot[]; titres: Titre[] }> {
  const titres = bibliotheque();
  const lots: Lot[] = [];
  await page.route("**/account.json", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const reponse = await route.fetch();
    const compte = (await reponse.json()) as Record<string, unknown>;
    await route.fulfill({ response: reponse, json: { ...compte, features: { bank_tidy: true, title_edits: true } } });
  });
  await page.route("**/media/titles.json*", async (route: Route) => {
    const tries = [...titres].sort((a, b) => a.title.localeCompare(b.title, "fr"));
    await route.fulfill({
      json: { titles: tries, total: 30, matched: 30, offset: 0, limit: 100, sort: "title", order: "asc", facets: {} },
    });
  });
  await page.route("**/media/titles/edit.json", async (route: Route) => {
    const lot = route.request().postDataJSON() as Lot;
    lots.push(lot);
    const genres = lot.titles.filter((entry) => entry.values.genre !== undefined && entry.values.genre !== "Jazz");
    const reponse = {
      dry_run: Boolean(lot.dry_run),
      entry: lot.dry_run ? null : lots.length,
      written: lot.titles.length,
      waiting: [],
      kept: [],
      refused: [],
      unchanged: 0,
      selections: lot.dry_run && genres.length ? [{ id: 1, name: "Jazz", gained: 0, lost: genres.length }] : [],
    };
    if (!lot.dry_run) {
      for (const entry of lot.titles) {
        const titre = titres.find((item) => item.id === entry.id);
        if (!titre) continue;
        for (const [champ, valeur] of Object.entries(entry.values)) {
          if (champ === "year") titre.year = valeur ? Number(valeur) : null;
          else (titre as Record<string, unknown>)[champ] = valeur;
        }
      }
    }
    await route.fulfill({ json: reponse });
  });
  return { lots, titres };
}

async function ouvrir(page: Page) {
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer&tri=title");
  const tableau = page.getByRole("region", { name: "Toute la banque" });
  await expect(tableau.getByRole("button", { name: "Titre 01", exact: true })).toBeVisible();
  return tableau;
}

const ligne = (page: Page, titre: string) =>
  page.getByRole("region", { name: "Toute la banque" }).locator("tbody tr").filter({ hasText: titre });

test("la colonne Album de 30 titres se remplit au clavier, sans souris", async ({ page }) => {
  const { lots, titres } = await tableur(page);
  await ouvrir(page);

  await ligne(page, "Titre 01").locator("td.c-album button").focus();
  for (let index = 0; index < 30; index += 1) {
    await page.keyboard.press("Enter");
    const champ = page.getByRole("textbox", { name: `Album de « Titre ${String(index + 1).padStart(2, "0")} »` });
    await expect(champ).toBeFocused();
    await page.keyboard.type("Ciel");
    // Entrée enregistre, et passe à la cellule du dessous.
    await page.keyboard.press("Enter");
    await expect(champ).toHaveCount(0);
  }

  expect(titres.every((titre) => titre.album === "Ciel")).toBe(true);
  expect(lots.filter((lot) => !lot.dry_run)).toHaveLength(30);
  await expect(ligne(page, "Titre 30").locator("td.c-album")).toHaveText("Ciel");
  await expect(avis(page, "Fiche de « Titre 30 » corrigée.")).toBeVisible();
});

test("un lecteur d'écran entend la cellule ouverte ; Échap l'annule, Tab passe à la suivante", async ({ page }) => {
  const { lots } = await tableur(page);
  await ouvrir(page);

  const album = ligne(page, "Titre 02").locator("td.c-album button");
  await album.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("textbox", { name: "Album de « Titre 02 »" })).toBeFocused();
  await expect(page.getByText("Cellule ouverte : Album de « Titre 02 ». Entrée enregistre, Échap annule.")).toBeAttached();

  await page.keyboard.type("Brouillon");
  await page.keyboard.press("Escape");
  await expect(album).toBeFocused();
  await expect(album).toHaveText("—vide");
  expect(lots).toHaveLength(0);

  // Les flèches passent d'une cellule à l'autre ; Tab enregistre et passe à la suivante.
  await page.keyboard.press("ArrowLeft");
  await expect(ligne(page, "Titre 02").locator("td.c-artist button")).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("Madame Orage");
  await page.keyboard.press("Tab");
  await expect(album).toBeFocused();
  await expect(ligne(page, "Titre 02").locator("td.c-artist")).toHaveText("Madame Orage");
  expect(lots.at(-1)?.titles).toEqual([{ id: 2, values: { artist: "Madame Orage" }, expected: { artist: "Orage" } }]);
});

test("un collage sur 30 titres sélectionnés demande confirmation", async ({ page }) => {
  const { lots, titres } = await tableur(page);
  const tableau = await ouvrir(page);

  await tableau.getByRole("checkbox", { name: "Tout sélectionner" }).focus();
  await page.keyboard.press("Space");
  await expect(tableau.getByRole("toolbar", { name: "Sélection" })).toContainText("30 titres sélectionnés");

  const album = ligne(page, "Titre 05").locator("td.c-album button");
  await album.focus();
  // Ce que Ctrl+V envoie à la cellule : le texte du presse-papiers.
  await album.evaluate((cellule) => {
    const donnees = new DataTransfer();
    donnees.setData("text/plain", "Ciel\n");
    cellule.dispatchEvent(new ClipboardEvent("paste", { clipboardData: donnees, bubbles: true, cancelable: true }));
  });

  const fenetre = page.getByRole("dialog", { name: "Écrire « Ciel » dans l'album de 30 titres ?" });
  await expect(fenetre.getByText("30 fiches changent.")).toBeVisible();
  expect(lots.every((lot) => lot.dry_run)).toBe(true);
  await fenetre.getByRole("button", { name: "Écrire 30 fiches" }).click();
  await expect(fenetre).toHaveCount(0);
  await expect(avis(page, "30 fiches corrigées.")).toBeVisible();
  expect(titres.every((titre) => titre.album === "Ciel")).toBe(true);
});

test("un genre garde son essai : la sélection qui perd le titre se dit avant d'écrire", async ({ page }) => {
  const { lots } = await tableur(page);
  await ouvrir(page);

  await ligne(page, "Titre 03").locator("td.c-genre button").focus();
  await page.keyboard.press("Enter");
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("Soul");
  await page.keyboard.press("Enter");

  const fenetre = page.getByRole("dialog", { name: "Corriger la fiche de « Titre 03 » ?" });
  await expect(fenetre.getByText("« Jazz » perd 1 titre.")).toBeVisible();
  expect(lots.every((lot) => lot.dry_run)).toBe(true);
  await fenetre.getByRole("button", { name: "Écrire 1 fiche" }).click();
  await expect(avis(page, "Fiche de « Titre 03 » corrigée.")).toBeVisible();
  await expect(ligne(page, "Titre 03").locator("td.c-genre")).toHaveText("Soul");
});
