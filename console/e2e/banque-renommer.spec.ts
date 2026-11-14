import type { Page, Route } from "@playwright/test";
import { verifierAccessibilite } from "./accessibilite.ts";
import { alerte, antenne, avis, expect, seConnecter, test } from "./banc.ts";

// Renommer des fichiers d'après leur fiche (FON-68). Le moteur du banc n'a ni
// bibliothèque Beets ni le rangement allumé : le parcours allume les
// interrupteurs dans /account.json, et tient ici une bibliothèque que l'aperçu,
// le renommage et « Annuler » lisent et changent comme le moteur
// (engine/radiotomate/services/title_renames.py). « Brume » est à l'antenne, et
// le nom de « Dune » est déjà pris.

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
type Demande = { ids: number[]; model: string; by_artist: boolean; dry_run: boolean };

function titre(id: number, title: string, artist: string, album: string, fichier: string): Titre {
  return {
    id,
    title,
    artist,
    album,
    year: 2020,
    genre: "Jazz",
    famille: "jazz",
    famille_label: "Jazz",
    duration: 180 + id,
    zone: "collections",
    collection: "jazz",
    path: `20-archives/jazz/${fichier}`,
    missing: [],
  };
}

function bibliotheque(): Titre[] {
  return [
    titre(1, "Comète", "Orage", "Ciel", "03_comete.mp3"),
    titre(2, "Été indien", "Orage", "Ciel", "04 ete indien.flac"),
    titre(3, "Brume", "Madame Orage", "", "brume.mp3"),
    titre(4, "Dune", "Zéphyr", "Sable", "dune.mp3"),
    titre(5, "Pris", "Zéphyr", "Sable", "Zéphyr - Dune.mp3"),
  ];
}

const etiquette = (entry: Titre) => `${entry.artist} – ${entry.title}`;

function cible(entry: Titre, modele: string, parArtiste: boolean): string {
  const parts = entry.path.split("/");
  const ext = parts.at(-1)!.replace(/^.*(\.[^.]+)$/, "$1");
  const nom = { "artiste-titre": `${entry.artist} - ${entry.title}`, "artiste-album-titre": `${entry.artist} - ${entry.album} - ${entry.title}`, titre: entry.title }[modele];
  const dossier = parArtiste ? [...parts.slice(0, 2), entry.artist] : parts.slice(0, -1);
  return [...dossier, `${nom}${ext}`].join("/");
}

/** Allume le rangement et le renommage, et tient la bibliothèque. Rend les demandes reçues. */
async function banque(page: Page): Promise<{ demandes: Demande[]; titres: Titre[] }> {
  const titres = bibliotheque();
  const demandes: Demande[] = [];
  const journal = new Map<number, Array<{ id: number; avant: string }>>();
  await page.route("**/account.json", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const reponse = await route.fetch();
    const compte = (await reponse.json()) as Record<string, unknown>;
    await route.fulfill({
      response: reponse,
      json: { ...compte, features: { bank_tidy: true, title_edits: true, bank_moves: true, title_renames: true } },
    });
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
        facets: { collection: [{ value: "jazz", label: "jazz", count: titres.length }] },
      },
    });
  });
  await page.route("**/media/titles/rename.json", async (route: Route) => {
    const demande = route.request().postDataJSON() as Demande;
    demandes.push(demande);
    const pris = new Set(titres.map((entry) => entry.path));
    const plans = demande.ids.map((id) => {
      const entry = titres.find((item) => item.id === id)!;
      const to = entry.album || demande.model !== "artiste-album-titre" ? cible(entry, demande.model, demande.by_artist) : null;
      const plan = { id, label: etiquette(entry), path: entry.path, to, state: "rename", reason: "" };
      if (!to) return { ...plan, state: "incomplete", reason: "La fiche n'a pas d'album." };
      if (to === entry.path) return { ...plan, state: "same", reason: "Il porte déjà ce nom." };
      if (id === 3) return { ...plan, state: "busy", reason: "À l'antenne en ce moment." };
      if (pris.has(to)) return { ...plan, state: "taken", reason: "Ce nom est déjà pris : rien n'est remplacé." };
      pris.add(to);
      return plan;
    });
    if (demande.dry_run) return route.fulfill({ json: { dry_run: true, titles: plans, entry: null, left: [] } });
    const faits = plans.filter((plan) => plan.state === "rename");
    const numero = journal.size + 1;
    journal.set(
      numero,
      faits.map((plan) => ({ id: plan.id, avant: plan.path })),
    );
    for (const plan of faits) titres.find((item) => item.id === plan.id)!.path = plan.to!;
    await route.fulfill({
      json: {
        dry_run: false,
        titles: plans.map((plan) => (plan.state === "rename" ? { ...plan, state: "renamed" } : plan)),
        entry: faits.length ? numero : null,
        left: [],
      },
    });
  });
  await page.route("**/media/journal/*/undo.json", async (route: Route) => {
    const numero = Number(route.request().url().match(/journal\/(\d+)\//)?.[1]);
    const changes = journal.get(numero) ?? [];
    for (const change of changes) titres.find((item) => item.id === change.id)!.path = change.avant;
    await route.fulfill({
      json: { dry_run: false, entry: numero + 100, written: changes.length, waiting: [], kept: [], refused: [], unchanged: 0, selections: [] },
    });
  });
  return { demandes, titres };
}

async function ouvrir(page: Page) {
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer");
  const tableau = page.getByRole("region", { name: "Toute la banque" });
  await expect(tableau.getByRole("button", { name: "Comète", exact: true })).toBeVisible();
  return tableau;
}

test("des fichiers se renomment d'après leur fiche, puis reprennent leur nom", async ({ page }) => {
  const { demandes, titres } = await banque(page);
  const tableau = await ouvrir(page);

  for (const nom of ["Comète", "Été indien", "Brume", "Dune"]) {
    await tableau.getByRole("checkbox", { name: `Sélectionner ${nom}` }).click();
  }
  await tableau.getByRole("button", { name: "Renommer" }).click();
  const fenetre = page.getByRole("dialog", { name: "Renommer 4 fichiers" });

  // L'aperçu dit le nom de chacun, ou pourquoi il garde le sien.
  const apercu = fenetre.getByRole("list", { name: "Aperçu des noms" });
  await expect(apercu.getByText("Orage - Comète.mp3")).toBeVisible();
  await expect(apercu.getByText("Orage - Été indien.flac")).toBeVisible();
  await expect(apercu.getByText("À l'antenne en ce moment.")).toBeVisible();
  await expect(apercu.getByText("Ce nom est déjà pris : rien n'est remplacé.")).toBeVisible();
  await expect(fenetre.getByText("2 fichiers prendront le nom de leur fiche.")).toBeVisible();
  await verifierAccessibilite(page, "la fenêtre « Renommer »");

  // Un autre modèle : l'aperçu se refait.
  await fenetre.getByRole("combobox", { name: "Modèle" }).click();
  await page.getByRole("option", { name: "Artiste - Album - Titre" }).click();
  await expect(apercu.getByText("Orage - Ciel - Comète.mp3")).toBeVisible();
  await expect(apercu.getByText("La fiche n'a pas d'album.")).toBeVisible();
  await fenetre.getByRole("combobox", { name: "Modèle" }).click();
  await page.getByRole("option", { name: "Artiste - Titre", exact: true }).click();
  await fenetre.getByRole("checkbox", { name: "Un dossier par artiste, dans sa collection" }).click();
  await expect(apercu.getByText("Orage/Orage - Comète.mp3")).toBeVisible();
  await fenetre.getByRole("checkbox", { name: "Un dossier par artiste, dans sa collection" }).click();

  await fenetre.getByRole("button", { name: "Renommer 2 fichiers" }).click();
  await expect(fenetre).toBeHidden();
  // Pas fait en entier : le message prend le ton d'un échec, et dit pourquoi.
  const fait = alerte(page, "2 fichiers renommés. 2 fichiers gardent leur nom. À l'antenne en ce moment. Ce nom est déjà pris : rien n'est remplacé.");
  await expect(fait).toBeVisible();
  expect(demandes.at(-1)).toEqual({ ids: [1, 2, 3, 4], model: "artiste-titre", by_artist: false, dry_run: false });
  expect(titres[0].path).toBe("20-archives/jazz/Orage - Comète.mp3");

  // « Annuler » rend leurs noms aux fichiers.
  await fait.getByRole("button", { name: "Annuler" }).click();
  await expect(avis(page, "2 fichiers ont repris leur nom d'avant.")).toBeVisible();
  expect(titres[0].path).toBe("20-archives/jazz/03_comete.mp3");
});

test("dans la fiche, « Renommer ainsi » quand le nom ne suit pas la fiche", async ({ page }) => {
  const { titres } = await banque(page);
  const tableau = await ouvrir(page);

  await tableau.getByRole("button", { name: "Comète", exact: true }).click();
  const fiche = page.getByRole("complementary", { name: "Fiche de Comète" });
  const nom = fiche.getByRole("region", { name: "Nom du fichier" });
  await expect(nom.getByText("Orage - Comète.mp3")).toBeVisible();

  await nom.getByRole("button", { name: "Renommer ainsi" }).click();
  await expect(avis(page, "1 fichier renommé.")).toBeVisible();
  expect(titres[0].path).toBe("20-archives/jazz/Orage - Comète.mp3");
  // Le fichier porte maintenant le nom de sa fiche : plus rien à proposer.
  await expect(fiche.getByRole("region", { name: "Nom du fichier" })).toHaveCount(0);
});
