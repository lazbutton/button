import type { Page, Route } from "@playwright/test";
import { verifierAccessibilite } from "./accessibilite.ts";
import { antenne, avis, expect, seConnecter, test } from "./banc.ts";

// Corriger la fiche d'un titre ou d'un lot (FON-66). Le moteur du banc n'a ni
// bibliothèque Beets, ni le rangement allumé : le parcours allume les deux
// interrupteurs dans /account.json, et tient ici une bibliothèque que les routes
// du tableau, de l'écriture et de « Revenir » lisent et changent comme le moteur
// (engine/radiotomate/services/title_edits.py). « Brume » est à l'antenne, et le
// fichier de « Dune » ne s'écrit pas.

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

const FAMILLES: Record<string, string> = { jazz: "Jazz", "soul-funk": "Soul, funk", "": "" };

function titre(id: number, title: string, artist: string, album: string, year: number | null, genre: string): Titre {
  return {
    id,
    title,
    artist,
    album,
    year,
    genre,
    famille: genre === "Jazz" ? "jazz" : "",
    famille_label: genre === "Jazz" ? "Jazz" : "",
    duration: 180 + id,
    zone: "rotation",
    collection: "rotation",
    path: `10-rotation/${id}.mp3`,
    missing: [],
  };
}

function bibliotheque(): Titre[] {
  return [
    titre(1, "Comète", "Orage", "Ciel", 2015, "Jazz"),
    titre(2, "Été indien", "Orage", "Ciel", 2019, "Jazz"),
    titre(3, "Brume", "Madame Orage", "", null, ""),
    titre(4, "Dune", "Zéphyr", "Sable", 2021, "Électro"),
  ];
}

const etiquette = (entry: Titre) => `${entry.artist} – ${entry.title}`;

function valeur(entry: Titre, champ: Champ): string {
  return champ === "year" ? (entry.year ? String(entry.year) : "") : entry[champ];
}

function poser(entry: Titre, champ: Champ, texte: string) {
  if (champ === "year") entry.year = texte ? Number(texte) : null;
  else entry[champ] = texte;
  if (champ === "famille") entry.famille_label = FAMILLES[texte] ?? texte;
}

/** Allume le rangement et la correction, et tient la bibliothèque. Rend les lots reçus. */
async function banque(page: Page, correction = true): Promise<{ lots: Lot[]; titres: Titre[] }> {
  const titres = bibliotheque();
  const lots: Lot[] = [];
  const journal = new Map<number, Array<{ id: number; champ: Champ; avant: string; apres: string }>>();
  await page.route("**/account.json", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const reponse = await route.fetch();
    const compte = (await reponse.json()) as Record<string, unknown>;
    await route.fulfill({ response: reponse, json: { ...compte, features: { bank_tidy: true, title_edits: correction } } });
  });
  await page.route("**/media/titles.json*", async (route: Route) => {
    await route.fulfill({
      json: {
        titles: titres,
        total: titres.length,
        matched: titres.length,
        offset: 0,
        limit: 100,
        sort: "artist",
        order: "asc",
        facets: { collection: [{ value: "rotation", label: "rotation", count: titres.length }] },
      },
    });
  });
  await page.route("**/media/titles/edit.json", async (route: Route) => {
    const lot = route.request().postDataJSON() as Lot;
    lots.push(lot);
    const refused = [];
    const waiting = [];
    const ecrits: Array<{ entry: Titre; valeurs: Partial<Record<Champ, string>> }> = [];
    const perdus = new Set<number>();
    let unchanged = 0;
    for (const demande of lot.titles) {
      const entry = titres.find((item) => item.id === demande.id);
      if (!entry) continue;
      const changes = Object.entries(demande.values).filter(([champ, texte]) => valeur(entry, champ as Champ) !== texte);
      if (!changes.length) {
        unchanged += 1;
        continue;
      }
      if (entry.id === 4) {
        refused.push({ id: 4, label: etiquette(entry), code: "read_only", reason: "Le moteur n'a pas le droit d'écrire son fichier." });
        continue;
      }
      if (entry.genre === "Jazz" && demande.values.genre !== undefined && demande.values.genre !== "Jazz") perdus.add(entry.id);
      if (entry.id === 3) {
        waiting.push({ id: 3, label: etiquette(entry), code: "on_air", reason: "Il est à l'antenne : sa fiche s'écrira quand il sera passé." });
        continue;
      }
      ecrits.push({ entry, valeurs: Object.fromEntries(changes) });
    }
    const essai = {
      dry_run: Boolean(lot.dry_run),
      entry: null as number | null,
      written: ecrits.length,
      waiting,
      kept: [],
      refused,
      unchanged,
      selections: perdus.size ? [{ id: 1, name: "Jazz", gained: 0, lost: perdus.size }] : [],
    };
    if (lot.dry_run) return route.fulfill({ json: essai });
    if (refused.length) {
      return route.fulfill({
        status: 409,
        json: { error: "Rien n'a été écrit.", code: "titles_refused", message: "Rien n'a été écrit.", titles: refused },
      });
    }
    const numero = journal.size + 1;
    journal.set(
      numero,
      ecrits.flatMap(({ entry, valeurs }) =>
        Object.entries(valeurs).map(([champ, apres]) => ({ id: entry.id, champ: champ as Champ, avant: valeur(entry, champ as Champ), apres: apres ?? "" })),
      ),
    );
    for (const { entry, valeurs } of ecrits) for (const [champ, texte] of Object.entries(valeurs)) poser(entry, champ as Champ, texte ?? "");
    await route.fulfill({ json: { ...essai, entry: numero, selections: [] } });
  });
  await page.route("**/media/journal/*/undo.json", async (route: Route) => {
    const numero = Number(route.request().url().match(/journal\/(\d+)\//)?.[1]);
    const changes = journal.get(numero) ?? [];
    const repris = new Set<number>();
    for (const change of changes) {
      const entry = titres.find((item) => item.id === change.id);
      if (!entry) continue;
      poser(entry, change.champ, change.avant);
      repris.add(entry.id);
    }
    await route.fulfill({
      json: { dry_run: false, entry: numero + 100, written: repris.size, waiting: [], kept: [], refused: [], unchanged: 0, selections: [] },
    });
  });
  return { lots, titres };
}

async function ouvrir(page: Page, role: "admin" | "programmateur" = "programmateur") {
  await seConnecter(page, role);
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer");
  const tableau = page.getByRole("region", { name: "Toute la banque" });
  await expect(tableau.getByRole("button", { name: "Comète", exact: true })).toBeVisible();
  return tableau;
}

test("la fiche d'un titre se corrige dans son panneau, puis revient", async ({ page }) => {
  const { lots } = await banque(page);
  const tableau = await ouvrir(page);

  await tableau.getByRole("button", { name: "Comète", exact: true }).click();
  const fiche = page.getByRole("complementary", { name: "Fiche de Comète" });
  await fiche.getByRole("button", { name: "Corriger la fiche" }).click();
  const formulaire = fiche.getByRole("form", { name: "Corriger la fiche" });
  await expect(formulaire.getByLabel("Album")).toHaveValue("Ciel");

  // Une année qui n'en est pas une ne part pas.
  await formulaire.getByLabel("Année").fill("15");
  await expect(formulaire.getByText("L'année s'écrit en quatre chiffres")).toBeVisible();
  await expect(formulaire.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
  await formulaire.getByLabel("Année").fill("2015");

  await formulaire.getByLabel("Album").fill("Nuages");
  await formulaire.getByRole("button", { name: "Enregistrer" }).click();
  await expect(avis(page, "Fiche de « Comète » corrigée.")).toBeVisible();
  await expect(fiche.getByText("Nuages")).toBeVisible();
  // Seul le champ changé part, avec ce que la console montrait.
  expect(lots.at(-1)?.titles).toEqual([{ id: 1, values: { album: "Nuages" }, expected: { album: "Ciel" } }]);

  // Au clavier : Échap referme le formulaire, puis la fiche.
  await fiche.getByRole("button", { name: "Corriger la fiche" }).click();
  await page.keyboard.press("Escape");
  await expect(fiche.getByRole("form", { name: "Corriger la fiche" })).toHaveCount(0);
  await expect(fiche.getByRole("heading", { name: "Fiche du titre" })).toBeFocused();

  await page.getByRole("button", { name: "Revenir" }).click();
  await expect(avis(page, "1 fiche a repris sa valeur d'avant.")).toBeVisible();
  await expect(fiche.getByText("Ciel")).toBeVisible();
});

test("modifier un lot : un champ coché pour tous, l'essai nomme les sélections touchées", async ({ page }) => {
  const { lots } = await banque(page);
  const tableau = await ouvrir(page, "admin");

  await tableau.getByRole("checkbox", { name: "Sélectionner Comète" }).click();
  await tableau.getByRole("checkbox", { name: "Sélectionner Été indien" }).click();
  await tableau.getByRole("checkbox", { name: "Sélectionner Dune" }).click();
  await tableau.getByRole("toolbar", { name: "Sélection" }).getByRole("button", { name: "Modifier 3 fiches" }).click();

  const fenetre = page.getByRole("dialog", { name: "Modifier 3 fiches" });
  await expect(fenetre.getByRole("button", { name: "Vérifier" })).toBeDisabled();
  await fenetre.getByRole("checkbox", { name: "Genre" }).click();
  await fenetre.getByLabel("Genre, pour tous les titres").fill("Soul");
  await fenetre.getByRole("button", { name: "Vérifier" }).click();

  // Le fichier de « Dune » ne s'écrit pas : rien ne part tant qu'il est dans le lot.
  await expect(fenetre.getByText("Un titre ne peut pas s'écrire")).toBeVisible();
  await expect(fenetre.getByText("Zéphyr – Dune : Le moteur n'a pas le droit d'écrire son fichier.")).toBeVisible();
  await fenetre.getByRole("button", { name: "Continuer sans ce titre" }).click();
  await expect(fenetre.getByText("Un titre a été retiré du lot.")).toBeVisible();
  await expect(fenetre.getByText("« Jazz » perd 2 titres.")).toBeVisible();
  expect(lots.every((lot) => lot.dry_run)).toBe(true);
  await verifierAccessibilite(page, "la fenêtre « Modifier N fiches », en clair");
  await page.emulateMedia({ colorScheme: "dark" });
  await verifierAccessibilite(page, "la fenêtre « Modifier N fiches », en sombre");
  await page.emulateMedia({ colorScheme: "light" });

  await fenetre.getByRole("button", { name: "Modifier 2 fiches" }).click();
  await expect(fenetre).toHaveCount(0);
  await expect(avis(page, "2 fiches corrigées.")).toBeVisible();
  expect(lots.at(-1)?.dry_run).toBe(false);
  expect(lots.at(-1)?.titles.map((entry) => entry.id)).toEqual([1, 2]);
  await expect(tableau.locator("tbody tr").filter({ hasText: "Comète" })).toContainText("Soul");
  await expect(tableau.locator("tbody tr").filter({ hasText: "Dune" })).toContainText("Électro");
});

test("un titre à l'antenne attend la fin de son passage", async ({ page }) => {
  await banque(page);
  const tableau = await ouvrir(page);

  await tableau.locator("tbody tr").filter({ hasText: "Brume" }).getByRole("button", { name: "Actions pour Brume" }).click();
  await page.getByRole("menuitem", { name: "Corriger la fiche" }).click();
  const fiche = page.getByRole("complementary", { name: "Fiche de Brume" });
  const formulaire = fiche.getByRole("form", { name: "Corriger la fiche" });
  await formulaire.getByLabel("Album").fill("Lisière");
  await formulaire.getByRole("button", { name: "Enregistrer" }).click();

  await expect(formulaire.getByText("Ce titre est à l'antenne ou en file")).toBeVisible();
  await formulaire.getByRole("button", { name: "Enregistrer quand même" }).click();
  await expect(avis(page, "La fiche de « Brume » s'écrira quand le titre aura fini de passer à l'antenne.")).toBeVisible();
});

test("la correction coupée sur la station, la fiche se lit sans se corriger", async ({ page }) => {
  await banque(page, false);
  const tableau = await ouvrir(page);

  // Un admin sélectionne encore, pour ajouter à un bac (FON-69), mais rien ne se corrige.
  await tableau.getByRole("checkbox", { name: "Sélectionner Comète" }).click();
  const selection = tableau.getByRole("toolbar", { name: "Sélection" });
  await expect(selection.getByRole("button", { name: "Ajouter à un bac" })).toBeVisible();
  await expect(selection.getByRole("button", { name: /^Modifier/ })).toHaveCount(0);
  await selection.getByRole("button", { name: "Désélectionner" }).click();
  await tableau.getByRole("button", { name: "Comète", exact: true }).click();
  const fiche = page.getByRole("complementary", { name: "Fiche de Comète" });
  await expect(fiche.getByText("Complète")).toBeVisible();
  await expect(fiche.getByRole("button", { name: "Corriger la fiche" })).toHaveCount(0);
});

/** Le tableau rangé par famille : les familles de la bibliothèque, comptées (FON-75). */
async function parFamille(page: Page, titres: Titre[]) {
  await page.route("**/media/titles.json*", async (route: Route) => {
    const famille = new URL(route.request().url()).searchParams.get("famille");
    const gardes = famille === null ? titres : titres.filter((entry) => entry.famille === famille);
    await route.fulfill({
      json: {
        titles: gardes,
        total: titres.length,
        matched: gardes.length,
        offset: 0,
        limit: 100,
        sort: "artist",
        order: "asc",
        facets: {
          famille: [
            { value: "jazz", label: "Jazz", count: titres.filter((entry) => entry.famille === "jazz").length },
            { value: "soul-funk", label: "Soul, funk", count: titres.filter((entry) => entry.famille === "soul-funk").length },
            { value: "", label: "", count: titres.filter((entry) => !entry.famille).length },
          ],
          collection: [{ value: "rotation", label: "rotation", count: titres.length }],
        },
      },
    });
  });
}

test("des titres glissés sur une famille demandent confirmation, puis la portent", async ({ page }) => {
  const { lots, titres } = await banque(page);
  await parFamille(page, titres);
  await seConnecter(page, "admin");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer&ranger=famille");
  const tableau = page.getByRole("region", { name: "Toute la banque" });
  await tableau.getByRole("checkbox", { name: "Sélectionner Comète" }).click();
  await tableau.getByRole("checkbox", { name: "Sélectionner Été indien" }).click();

  const colonne = page.getByRole("complementary", { name: "Ranger la banque" });
  await tableau.locator("tbody tr").filter({ hasText: "Comète" }).dragTo(colonne.getByRole("option", { name: /^Soul, funk/ }));
  const fenetre = page.getByRole("dialog", { name: "Modifier 2 fiches" });
  await expect(fenetre.getByRole("checkbox", { name: "Famille" })).toBeChecked();
  expect(lots).toEqual([]);
  await fenetre.getByRole("button", { name: "Vérifier" }).click();
  await fenetre.getByRole("button", { name: "Modifier 2 fiches" }).click();
  await expect(avis(page, "2 fiches corrigées.")).toBeVisible();
  expect(lots.at(-1)?.titles).toEqual([
    { id: 1, values: { famille: "soul-funk" }, expected: { famille: "jazz" } },
    { id: 2, values: { famille: "soul-funk" }, expected: { famille: "jazz" } },
  ]);
});

test("une cible refusée le dit : des titres glissés sur leur propre collection", async ({ page }) => {
  await banque(page);
  await seConnecter(page, "admin");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer");
  const tableau = page.getByRole("region", { name: "Toute la banque" });
  const colonne = page.getByRole("complementary", { name: "Ranger la banque" });
  await tableau.locator("tbody tr").filter({ hasText: "Comète" }).dragTo(colonne.getByRole("option", { name: /^Rotation/ }));
  await expect(page.getByRole("alert").or(page.getByRole("status")).filter({ hasText: "Ces titres sont déjà dans « Rotation »." })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
