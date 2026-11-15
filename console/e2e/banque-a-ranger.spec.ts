import type { Page, Route } from "@playwright/test";
import { verifierAccessibilite } from "./accessibilite.ts";
import { antenne, avis, expect, seConnecter, test } from "./banc.ts";

// Ce qui reste à ranger dans la banque (FON-92), qui remplace les vues Arrivées
// et Santé. Le moteur du banc n'a ni bibliothèque Beets ni le rangement allumé :
// le parcours allume les interrupteurs dans /account.json, et tient ici le
// compte de la santé (engine/radiotomate/services/bank_health.py) et celui des
// fiches à relire. Le premier compte tourne encore à la première demande ; une
// correction le refait, sans ce qu'elle a corrigé.

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
  guess?: { artist: string; title: string } | null;
};
type Lot = { titles: Array<{ id: number; values: Record<string, string>; expected: Record<string, string> }> };
type Envoi = { lot: Lot; dry_run: boolean };

function titre(id: number, artist: string, chemin: string, more: Partial<Titre> = {}): Titre {
  return {
    id,
    title: `Titre ${id}`,
    artist,
    album: "",
    year: null,
    genre: "",
    famille: "",
    famille_label: "",
    duration: 200 + id,
    zone: "rotation",
    collection: "rotation",
    path: `10-rotation/${chemin}`,
    missing: ["album", "year", "genre", "famille"],
    ...more,
  };
}

// promote-inbox.sh a pris le numéro de piste pour l'artiste.
const NUMEROS = [
  titre(1, "01", "01 - Ana Delta - Fado du port.mp3", {
    title: "01 - Ana Delta - Fado du port",
    guess: { artist: "Ana Delta", title: "Fado du port" },
  }),
  titre(2, "02", "02 - Ana Delta - Mille heures.mp3", {
    title: "Mille heures",
    guess: { artist: "Ana Delta", title: "Mille heures" },
  }),
  titre(3, "03", "03 - Intro.mp3", { title: "Intro", guess: null }),
];
const GRAPHIES = [
  titre(4, "Les Marées Hautes", "estuaire.mp3"),
  titre(5, "Les Marées Hautes", "delta.mp3"),
  titre(6, "les marees hautes", "ressac.mp3"),
];
const ARCHIVES = [
  titre(7, "Orage", "a.mp3", { genre: "Archive", genre_without: "" }),
  titre(8, "Orage", "b.mp3", { genre: "Rock, Archive", genre_without: "Rock" }),
];

function compte(etat: { numeros: boolean; graphies: boolean }) {
  return {
    model: "artiste-titre",
    figures: { titles: 93, complete: 0, families: [], without_family: 93 },
    spellings: etat.graphies
      ? {
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
        }
      : { count: 0, titles: 0, groups: [] },
    duplicates: {
      count: 1,
      titles: 2,
      groups: [
        {
          label: "Orage - Avant",
          titles: [titre(9, "Orage", "avant.mp3", { title: "Avant" }), titre(10, "Orage", "avant-bis.flac", { title: "Avant" })],
        },
      ],
    },
    misnamed: {
      count: 2,
      titles: [
        titre(11, "Zéphyr", "Comète.mp3", { title: "Comète", to: "Zéphyr - Comète.mp3" }),
        titre(12, "Orage Lent", "Avril.mp3", { title: "Avril", to: "Orage Lent - Avril.mp3" }),
      ],
    },
    numbered: etat.numeros ? { count: 3, titles: NUMEROS } : { count: 0, titles: [] },
    incomplete: {
      count: 93,
      fields: [
        { field: "title", count: 0 },
        { field: "artist", count: 2 },
        { field: "album", count: 40 },
        { field: "year", count: 60 },
        { field: "genre", count: 12 },
        { field: "famille", count: 93 },
      ],
    },
    archive: { count: 2, titles: ARCHIVES },
    unindexed: { count: 1, paths: ["10-rotation/abime.mp3"] },
  };
}

const FICHES = {
  enabled: true,
  progress: { library: 93, searched: 93, remaining_hours: null },
  statuses: { trouvé: 2 },
  levels: [{ value: "sûr", count: 2 }],
  fields: [],
  states: [],
  banks: [{ value: "rotation", count: 2 }],
  failures: [],
  titles: [],
  total: 2,
  next: null,
};

/** Allume le rangement et sa santé, tient les deux comptes, et rend les lots reçus. */
async function banc(page: Page): Promise<{ envois: Envoi[] }> {
  const envois: Envoi[] = [];
  const etat = { numeros: true, graphies: true };
  let demandes = 0;
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
      json: { computing: false, computed_at: "2026-11-15T11:57+01:00", error: null, health: compte(etat) },
    });
  });
  await page.route("**/fiches.json*", (route: Route) => route.fulfill({ json: FICHES }));
  await page.route("**/media/titles/edit.json", async (route: Route) => {
    const corps = route.request().postDataJSON() as Lot & { dry_run: boolean };
    envois.push({ lot: { titles: corps.titles }, dry_run: corps.dry_run });
    if (!corps.dry_run && corps.titles.some((item) => item.values.title)) etat.numeros = false;
    if (!corps.dry_run && corps.titles.some((item) => item.values.artist === "Les Marées Hautes")) etat.graphies = false;
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
  await page.route("**/media/titles/rename.json", async (route: Route) => {
    const demande = route.request().postDataJSON() as { ids: number[]; dry_run: boolean };
    const noms: Record<number, [string, string]> = {
      11: ["10-rotation/Comète.mp3", "10-rotation/Zéphyr - Comète.mp3"],
      12: ["10-rotation/Avril.mp3", "10-rotation/Orage Lent - Avril.mp3"],
    };
    const titles = demande.ids.map((id) => ({ id, label: `Titre ${id}`, path: noms[id][0], to: noms[id][1], state: "rename", reason: "" }));
    await route.fulfill({ json: { dry_run: demande.dry_run, titles, entry: null, left: [] } });
  });
  await page.route("**/media/titles.json*", async (route: Route) => {
    await route.fulfill({
      json: {
        titles: [],
        total: 0,
        matched: 0,
        offset: 0,
        limit: 100,
        sort: "artist",
        order: "asc",
        facets: { artist: [{ value: "", label: "Sans artiste", count: 2 }] },
      },
    });
  });
  return { envois };
}

async function ouvrir(page: Page, vue = "a-ranger") {
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto(`/sons?onglet=importer&vue=${vue}`);
  await expect(page.getByRole("heading", { name: "À ranger", level: 2 })).toBeVisible();
}

function tache(page: Page, titre: string) {
  return page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: titre, level: 3 }) });
}

test("« À ranger » dit ce qui reste à faire, le nom des fichiers à la fin, et l'onglet le compte", async ({ page }) => {
  await banc(page);
  await ouvrir(page);

  const aFaire = page.getByRole("list", { name: "À faire" });
  await expect(aFaire.getByRole("heading", { level: 3 })).toHaveText([
    "1 fichier n'est pas dans la bibliothèque",
    "3 titres ont un numéro pour artiste",
    "2 titres sans artiste",
    "2 titres ont des corrections trouvées en ligne",
    "1 artiste s'écrit de plusieurs façons",
    "1 titre est en double",
    "2 fiches portent le genre « Archive »",
  ]);
  await expect(page.getByRole("radio", { name: /^À ranger/ })).toContainText("7");
  const facultatif = page.getByRole("region", { name: "Facultatif" });
  await expect(facultatif.getByRole("heading", { name: "2 fichiers ne s'appellent pas « Artiste - Titre »" })).toBeVisible();
  await expect(facultatif.getByText("Comète.mp3 → Zéphyr - Comète.mp3")).toBeVisible();
  // Plus de chiffres sans geste : ni fiches complètes, ni familles.
  await expect(page.getByText(/fiches complètes|Aucune famille/)).toHaveCount(0);
  await expect(page.getByText("93 titres dans la banque.")).toBeVisible();
  await expect(page.getByText("Vérifié aujourd’hui à 11:57.").or(page.getByText(/Vérifié le 15\/11 à 11:57\./))).toBeVisible();
  await verifierAccessibilite(page, "la vue À ranger");

  // L'adresse de l'ancienne vue Santé ouvre « À ranger ».
  await page.goto("/sons?onglet=importer&vue=sante");
  await expect(page.getByRole("list", { name: "À faire" })).toBeVisible();
});

test("un numéro pris pour artiste se corrige d'après le nom du fichier", async ({ page }) => {
  const { envois } = await banc(page);
  await ouvrir(page);

  const numeros = tache(page, "3 titres ont un numéro pour artiste");
  await expect(numeros.getByText("L'antenne affiche « 01 », « 02 »… à la place de l'artiste.")).toBeVisible();
  await expect(
    numeros.getByText("01 - Ana Delta - Fado du port.mp3 → Ana Delta – Fado du port"),
  ).toBeVisible();
  // « 03 - Intro.mp3 » ne dit pas l'artiste : il se corrige dans le tableau.
  await expect(numeros.getByText(/Le nom d'un fichier n'en dit pas plus/)).toBeVisible();

  await numeros.getByRole("button", { name: "Corriger les 2 d'après leur nom" }).click();
  const confirmation = page.getByRole("dialog", { name: "Corriger 2 fiches d'après le nom du fichier ?" });
  await confirmation.getByRole("button", { name: "Écrire 2 fiches" }).click();
  await expect(confirmation).toBeHidden();
  await expect(avis(page, "2 fiches corrigées.")).toBeVisible();
  const ecrit = envois.find((envoi) => !envoi.dry_run)!;
  expect(ecrit.lot.titles).toEqual([
    {
      id: 1,
      values: { artist: "Ana Delta", title: "Fado du port" },
      expected: { artist: "01", title: "01 - Ana Delta - Fado du port" },
    },
    {
      id: 2,
      values: { artist: "Ana Delta", title: "Mille heures" },
      expected: { artist: "02", title: "Mille heures" },
    },
  ]);
  // Le compte refait n'a plus la tâche, et l'onglet compte une tâche de moins.
  await expect(page.getByRole("heading", { name: "3 titres ont un numéro pour artiste" })).toBeHidden();
  await expect(page.getByRole("radio", { name: /^À ranger/ })).toContainText("6");
});

test("un artiste écrit de plusieurs façons prend la graphie choisie", async ({ page }) => {
  const { envois } = await banc(page);
  await ouvrir(page);

  const graphies = tache(page, "1 artiste s'écrit de plusieurs façons");
  await expect(graphies.getByText("Les Marées Hautes (2) · les marees hautes (1)")).toBeVisible();
  await graphies.getByRole("button", { name: "Unifier « Les Marées Hautes »" }).click();
  const fenetre = page.getByRole("dialog", { name: "Écrire cet artiste d'une seule façon" });
  // La graphie la plus fréquente est déjà choisie.
  await expect(fenetre.getByRole("radio", { name: /^Les Marées Hautes/ })).toBeChecked();
  await fenetre.getByRole("button", { name: "Écrire « Les Marées Hautes » sur 1 titre" }).click();
  await expect(fenetre).toBeHidden();
  await expect(avis(page, "1 fiche corrigée.")).toBeVisible();
  // Un essai, puis l'écriture, sur le seul titre qui n'avait pas cette graphie.
  expect(envois.map((envoi) => envoi.dry_run)).toEqual([true, false]);
  expect(envois[1].lot.titles).toEqual([
    { id: 6, values: { artist: "Les Marées Hautes" }, expected: { artist: "les marees hautes" } },
  ]);
  await expect(page.getByRole("heading", { name: "1 artiste s'écrit de plusieurs façons" })).toBeHidden();
  await expect(page.getByText(/Rien à signaler : orthographe des artistes/)).toBeVisible();
});

test("« Archive » se retire après confirmation, et un artiste manquant ouvre le tableau", async ({ page }) => {
  const { envois } = await banc(page);
  await ouvrir(page);

  await tache(page, "2 fiches portent le genre « Archive »")
    .getByRole("button", { name: "Retirer « Archive » de 2 fiches" })
    .click();
  const confirmation = page.getByRole("dialog", { name: "Retirer « Archive » de 2 fiches ?" });
  await confirmation.getByRole("button", { name: "Écrire 2 fiches" }).click();
  await expect(confirmation).toBeHidden();
  const ecrit = envois.find((envoi) => !envoi.dry_run)!;
  expect(ecrit.lot.titles).toEqual([
    { id: 7, values: { genre: "" }, expected: { genre: "Archive" } },
    { id: 8, values: { genre: "Rock" }, expected: { genre: "Rock, Archive" } },
  ]);

  await tache(page, "2 titres sans artiste").getByRole("button", { name: "Compléter dans le tableau" }).click();
  await expect(page).toHaveURL(/ranger=artist&groupe=(&|$)/);
  await expect(page.getByRole("heading", { name: "À ranger", level: 2 })).toBeHidden();
});

test("les noms de fichiers se renomment à part, et la relecture s'ouvre depuis sa tâche", async ({ page }) => {
  await banc(page);
  await ouvrir(page);

  await page.getByRole("region", { name: "Facultatif" }).getByRole("button", { name: "Renommer…" }).click();
  const renommer = page.getByRole("dialog", { name: "Renommer 2 fichiers" });
  await expect(renommer.getByText("Zéphyr - Comète.mp3")).toBeVisible();
  await renommer.getByRole("button", { name: "Annuler" }).click();
  await expect(renommer).toBeHidden();

  await tache(page, "2 titres ont des corrections trouvées en ligne").getByRole("button", { name: "Relire" }).click();
  await expect(page).toHaveURL(/vue=relire/);
  await expect(page.getByRole("region", { name: "Fiches à relire" })).toBeVisible();
  // « À ranger » reste l'onglet choisi, et le retour y ramène.
  await expect(page.getByRole("radio", { name: /^À ranger/ })).toBeChecked();
  await page.getByRole("button", { name: "Retour à « À ranger »" }).click();
  await expect(page.getByRole("list", { name: "À faire" })).toBeVisible();
});
