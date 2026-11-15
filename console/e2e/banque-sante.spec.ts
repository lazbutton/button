import type { Page, Route } from "@playwright/test";
import { verifierAccessibilite } from "./accessibilite.ts";
import { antenne, avis, expect, seConnecter, test } from "./banc.ts";

// La santé de la banque (FON-72). Le moteur du banc n'a ni bibliothèque Beets ni
// le rangement allumé : le parcours allume les interrupteurs dans /account.json,
// et tient ici le compte que rend le moteur (engine/radiotomate/services/bank_health.py).
// Le premier compte tourne encore à la première demande ; une correction le
// refait, sans l'artiste corrigé.

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
  to?: string;
  genre_without?: string;
};
type Lot = { titles: Array<{ id: number; values: Record<string, string>; expected: Record<string, string> }> };
type Envoi = { lot: Lot; dry_run: boolean };

function titre(id: number, artist: string, fichier: string, more: Partial<Titre> = {}): Titre {
  return {
    id,
    title: `Titre ${id}`,
    artist,
    album: "Delta",
    year: 2020,
    genre: "Jazz",
    famille: "jazz",
    famille_label: "Jazz",
    duration: 200 + id,
    zone: "collections",
    collection: "nuit",
    path: `20-archives/nuit/${fichier}`,
    missing: [],
    ...more,
  };
}

const GRAPHIES = [
  titre(1, "Les Marées Hautes", "1.mp3"),
  titre(2, "Les Marées Hautes", "2.mp3"),
  titre(3, "les marees hautes", "3.mp3"),
];
const ARCHIVES = [
  titre(6, "Orage", "a.mp3", { genre: "Archive", genre_without: "" }),
  titre(7, "Orage", "b.mp3", { genre: "Rock, Archive", genre_without: "Rock" }),
];

function compte(corrige: boolean) {
  return {
    model: "artiste-titre",
    figures: {
      titles: 8,
      complete: 7,
      families: [
        { value: "jazz", label: "Jazz", count: 5 },
        { value: "rock", label: "Rock", count: 2 },
      ],
      without_family: 1,
    },
    spellings: corrige
      ? { count: 0, titles: 0, groups: [] }
      : {
          count: 1,
          titles: 3,
          groups: [
            {
              key: "lesmareeshautes",
              spellings: [
                { value: "Les Marées Hautes", count: 2 },
                { value: "les marees hautes", count: 1 },
              ],
              suggested: "Les Marées Hautes",
              count: 3,
              titles: GRAPHIES,
            },
          ],
        },
    duplicates: {
      count: 1,
      titles: 2,
      groups: [{ label: "Orage - Avant", titles: [titre(8, "Orage", "avant.mp3"), titre(9, "Orage", "avant-bis.flac")] }],
    },
    misnamed: {
      count: 2,
      titles: [
        titre(1, "Les Marées Hautes", "1.mp3", { to: "Les Marées Hautes - Titre 1.mp3" }),
        titre(6, "Orage", "a.mp3", { to: "Orage - Titre 6.mp3" }),
      ],
    },
    incomplete: {
      count: 1,
      fields: [
        { field: "title", count: 0 },
        { field: "artist", count: 0 },
        { field: "album", count: 1 },
        { field: "year", count: 1 },
        { field: "genre", count: 0 },
        { field: "famille", count: 1 },
      ],
    },
    archive: { count: 2, titles: ARCHIVES },
    unindexed: { count: 1, paths: ["20-archives/nuit/orphelin.flac"] },
  };
}

/** Allume le rangement et sa santé, et tient le compte. Rend les lots reçus. */
async function sante(page: Page): Promise<{ envois: Envoi[] }> {
  const envois: Envoi[] = [];
  let demandes = 0;
  let corrige = false;
  await page.route("**/account.json", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const reponse = await route.fetch();
    const compteJson = (await reponse.json()) as Record<string, unknown>;
    await route.fulfill({
      response: reponse,
      json: {
        ...compteJson,
        features: { bank_tidy: true, title_edits: true, bank_moves: true, title_renames: true, bank_health: true },
      },
    });
  });
  await page.route("**/media/health.json*", async (route: Route) => {
    demandes += 1;
    // La première demande trouve le compte en cours.
    if (demandes === 1) return route.fulfill({ json: { computing: true, computed_at: null, error: null, health: null } });
    await route.fulfill({
      json: { computing: false, computed_at: "2026-11-15T10:05+01:00", error: null, health: compte(corrige) },
    });
  });
  await page.route("**/media/titles/edit.json", async (route: Route) => {
    const corps = route.request().postDataJSON() as Lot & { dry_run: boolean };
    envois.push({ lot: { titles: corps.titles }, dry_run: corps.dry_run });
    if (!corps.dry_run && corps.titles.some((item) => item.values.artist)) corrige = true;
    await route.fulfill({
      json: {
        dry_run: corps.dry_run,
        entry: corps.dry_run ? null : 12,
        written: corps.titles.length,
        waiting: [],
        kept: [],
        refused: [],
        unchanged: 0,
        selections: [],
      },
    });
  });
  await page.route("**/media/titles.json*", async (route: Route) => {
    const titres = [...GRAPHIES, ...ARCHIVES];
    await route.fulfill({
      json: {
        titles: titres,
        total: titres.length,
        matched: titres.length,
        offset: 0,
        limit: 100,
        sort: "artist",
        order: "asc",
        facets: { album: [{ value: "", label: "Sans album", count: 1 }] },
      },
    });
  });
  return { envois };
}

async function ouvrir(page: Page) {
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer&vue=sante");
  await expect(page.getByRole("heading", { name: "Santé de la banque" })).toBeVisible();
  // Le compte tourne d'abord, puis la vue redemande.
  await expect(page.getByRole("region", { name: "La banque en chiffres" })).toBeVisible();
}

test("la santé compte ce qui cloche, et une correction le retire du compte", async ({ page }) => {
  const { envois } = await sante(page);
  await ouvrir(page);

  const chiffres = page.getByRole("region", { name: "La banque en chiffres" });
  await expect(chiffres.getByText("7 sur 8 fiches complètes, 88 %")).toBeVisible();
  await expect(chiffres.getByText("2 familles : Jazz (5), Rock (2)")).toBeVisible();
  await expect(page.getByText("Compté aujourd’hui à 10:05.").or(page.getByText(/Compté le 15\/11 à 10:05\./))).toBeVisible();

  const graphies = page.getByRole("region", { name: /Artistes écrits de plusieurs façons/ });
  await expect(graphies.getByText("« Les Marées Hautes » s'écrit de 2 façons, sur 3 titres")).toBeVisible();
  await expect(page.getByRole("region", { name: /Fichiers absents de la bibliothèque/ }).getByText("20-archives/nuit/orphelin.flac")).toBeVisible();
  await expect(page.getByRole("region", { name: /Fichiers mal nommés/ }).getByText("1.mp3 → Les Marées Hautes - Titre 1.mp3")).toBeVisible();
  await verifierAccessibilite(page, "la vue Santé de la banque");

  // « Écrire partout » ouvre la correction du lot, l'artiste coché et rempli.
  await graphies.getByRole("button", { name: "Écrire partout « Les Marées Hautes »" }).click();
  const fenetre = page.getByRole("dialog", { name: "Modifier 3 fiches" });
  await expect(fenetre.getByRole("textbox", { name: "Artiste, pour tous les titres" })).toHaveValue("Les Marées Hautes");
  await fenetre.getByRole("button", { name: "Vérifier" }).click();
  await fenetre.getByRole("button", { name: "Modifier 3 fiches" }).click();
  await expect(fenetre).toBeHidden();
  await expect(avis(page, "3 fiches corrigées.")).toBeVisible();
  const ecrit = envois.find((envoi) => !envoi.dry_run)!;
  expect(ecrit.lot.titles.map((item) => [item.id, item.values.artist])).toEqual([
    [1, "Les Marées Hautes"],
    [2, "Les Marées Hautes"],
    [3, "Les Marées Hautes"],
  ]);

  // Le compte refait n'a plus cet artiste.
  await expect(graphies.getByText("Rien à signaler")).toBeVisible();
});

test("« Archive » se retire en gardant les autres genres, et un champ vide ouvre le tableau", async ({ page }) => {
  const { envois } = await sante(page);
  await ouvrir(page);

  const archive = page.getByRole("region", { name: /Genre « Archive »/ });
  await archive.getByRole("button", { name: "Retirer « Archive » de 2 fiches" }).click();
  const confirmation = page.getByRole("dialog", { name: "Retirer « Archive » de 2 fiches ?" });
  await confirmation.getByRole("button", { name: "Écrire 2 fiches" }).click();
  await expect(confirmation).toBeHidden();
  const ecrit = envois.find((envoi) => !envoi.dry_run)!;
  expect(ecrit.lot.titles).toEqual([
    { id: 6, values: { genre: "" }, expected: { genre: "Archive" } },
    { id: 7, values: { genre: "Rock" }, expected: { genre: "Rock, Archive" } },
  ]);

  const incompletes = page.getByRole("region", { name: /Fiches incomplètes/ });
  await expect(incompletes.getByText("1 fiche sans année")).toBeVisible();
  await incompletes
    .getByRole("listitem")
    .filter({ hasText: "1 fiche sans album" })
    .getByRole("button", { name: "Voir dans le tableau" })
    .click();
  await expect(page).toHaveURL(/ranger=album&groupe=(&|$)/);
  await expect(page.getByRole("heading", { name: "Santé de la banque" })).toBeHidden();
});
