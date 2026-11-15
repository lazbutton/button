import type { Page, Route } from "@playwright/test";
import { verifierAccessibilite } from "./accessibilite.ts";
import { antenne, avis, expect, seConnecter, test } from "./banc.ts";

// Les arrivées de la banque (FON-81). Le moteur du banc n'a ni bibliothèque Beets
// ni le rangement allumé : le parcours allume les interrupteurs dans
// /account.json, et tient ici les arrivées que rend le moteur
// (engine/radiotomate/services/bank_arrivals.py). Accepter une proposition la
// retire de la liste, renommer donne au fichier son nom : comme le moteur.

type Proposition = { id: number; field: string; before: string; value: string; level: string; why: string; source: string; state: string; error: string };
type Arrivee = {
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
  added: string;
  searched: boolean;
  status: string;
  level: string;
  propositions: Proposition[];
  sure: number[];
  review: boolean;
  to: string | null;
  ready: boolean;
  duplicates: Array<{ id: number; title: string; artist: string; duration: number; zone: string; collection: string; path: string }>;
};

function proposition(id: number, field: string, before: string, value: string, level = "sûr"): Proposition {
  return { id, field, before, value, level, why: "", source: "deezer", state: "proposée", error: "" };
}

function nouveaute(n: number): Arrivee {
  const artist = `Groupe ${n}`;
  const title = `Morceau ${n}`;
  return {
    id: n,
    title: title.toLowerCase(),
    artist: artist.toLowerCase(),
    album: "",
    year: null,
    genre: "",
    famille: "",
    famille_label: "",
    duration: 180 + n,
    zone: "collections",
    collection: "nouveautes",
    path: `20-archives/nouveautes/piste-${n}.mp3`,
    missing: ["album", "year", "genre", "famille"],
    added: "2026-11-15T09:00+01:00",
    searched: true,
    status: "trouvé",
    level: "sûr",
    propositions: [proposition(100 + n, "artist", artist.toLowerCase(), artist), proposition(200 + n, "title", title.toLowerCase(), title)],
    sure: [100 + n, 200 + n],
    review: false,
    to: `${artist} - ${title}.mp3`,
    ready: true,
    duplicates: [],
  };
}

/** Une arrivée à relire, une pas encore cherchée et doublon d'un titre ancien. */
function autres(): Arrivee[] {
  const relire = nouveaute(21);
  relire.propositions = [proposition(121, "artist", "groupe 21", "Le Groupe 21", "à revoir")];
  relire.sure = [];
  relire.review = true;
  relire.ready = false;
  relire.to = "groupe 21 - morceau 21.mp3";
  const doublon = nouveaute(22);
  Object.assign(doublon, {
    searched: false,
    status: "",
    level: "",
    propositions: [],
    sure: [],
    to: null,
    ready: false,
    path: "20-archives/nouveautes/groupe 22 - morceau 22.mp3",
    duplicates: [{ id: 99, title: "morceau 22", artist: "groupe 22", duration: 202, zone: "rotation", collection: "rotation", path: "10-rotation/ancien.mp3" }],
  });
  return [relire, doublon];
}

type Demandes = { decisions: Array<{ accept?: number[]; refuse?: number[] }>; renommages: Array<{ ids: number[]; model: string; by_artist: boolean; dry_run: boolean }> };

async function arrivees(page: Page, liste: Arrivee[]): Promise<Demandes> {
  const demandes: Demandes = { decisions: [], renommages: [] };
  await page.route("**/account.json", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const reponse = await route.fetch();
    const compte = (await reponse.json()) as Record<string, unknown>;
    await route.fulfill({
      response: reponse,
      json: { ...compte, features: { bank_tidy: true, title_edits: true, bank_moves: true, title_renames: true, bank_arrivals: true } },
    });
  });
  await page.route("**/media/arrivals.json*", async (route: Route) => {
    const titres = liste.map((titre) => ({ ...titre, ready: !titre.review && Boolean(titre.sure.length || titre.to) }));
    await route.fulfill({
      json: {
        days: 30,
        model: "artiste-titre",
        total: titres.length,
        ready: titres.filter((titre) => titre.ready).length,
        review: titres.filter((titre) => titre.review).length,
        waiting: titres.filter((titre) => !titre.searched).length,
        duplicates: titres.filter((titre) => titre.duplicates.length).length,
        titles: titres,
      },
    });
  });
  await page.route("**/fiches/decisions.json", async (route: Route) => {
    const corps = route.request().postDataJSON() as { accept?: number[]; refuse?: number[] };
    demandes.decisions.push(corps);
    const prises = new Set([...(corps.accept ?? []), ...(corps.refuse ?? [])]);
    for (const titre of liste) {
      titre.propositions = titre.propositions.filter((one) => !prises.has(one.id));
      titre.sure = titre.sure.filter((id) => !prises.has(id));
      titre.review = titre.propositions.some((one) => one.level !== "sûr");
    }
    await route.fulfill({
      json: { accepted: corps.accept?.length ?? 0, refused: corps.refuse?.length ?? 0, written: corps.accept?.length ?? 0, waiting: [], failed: [], stale: 0, entry: 7 },
    });
  });
  await page.route("**/media/titles/rename.json", async (route: Route) => {
    const corps = route.request().postDataJSON() as Demandes["renommages"][number];
    demandes.renommages.push(corps);
    const plans = corps.ids.map((id) => {
      const titre = liste.find((item) => item.id === id)!;
      const to = `${titre.path.split("/").slice(0, -1).join("/")}/${titre.to}`;
      const avant = titre.path;
      if (!corps.dry_run) {
        titre.path = to;
        titre.to = null;
      }
      return { id, label: `${titre.artist} – ${titre.title}`, path: avant, to, state: corps.dry_run ? "rename" : "renamed", reason: "" };
    });
    await route.fulfill({ json: { dry_run: corps.dry_run, titles: plans, entry: corps.dry_run ? null : 8, left: [] } });
  });
  return demandes;
}

async function ouvrir(page: Page) {
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer");
}

test("vingt nouveautés se rangent en trois clics, fiches et noms compris", async ({ page }) => {
  const liste = Array.from({ length: 20 }, (_, index) => nouveaute(index + 1));
  const demandes = await arrivees(page, liste);
  await ouvrir(page);

  // 1. La vue Arrivées.
  await page.getByRole("radio", { name: "Arrivées" }).click();
  await expect(page.getByText("20 titres arrivés en 30 jours, 20 prêts à ranger.")).toBeVisible();
  const titres = page.getByRole("list", { name: "Titres arrivés" });
  await expect(titres.getByText("Nom : piste-1.mp3 → Groupe 1 - Morceau 1.mp3")).toBeVisible();
  await expect(titres.getByRole("list", { name: "Fiche proposée pour groupe 1 – morceau 1" }).getByText("Artiste : groupe 1 → Groupe 1")).toBeVisible();
  await verifierAccessibilite(page, "la vue Arrivées");

  // 2. « Ranger les 20 sûrs », 3. la confirmation.
  await page.getByRole("button", { name: "Ranger les 20 sûrs" }).click();
  const confirmation = page.getByRole("alertdialog", { name: "Ranger les 20 sûrs ?" }).or(page.getByRole("dialog", { name: "Ranger les 20 sûrs ?" }));
  await expect(confirmation.getByText("40 propositions sûres acceptées, 20 fichiers renommés.", { exact: false })).toBeVisible();
  await confirmation.getByRole("button", { name: "Ranger les 20 sûrs" }).click();

  await expect(avis(page, "20 titres rangés : 40 valeurs écrites, 20 fichiers renommés.")).toBeVisible();
  expect(demandes.decisions).toEqual([{ accept: liste.flatMap((titre) => [100 + titre.id, 200 + titre.id]) }]);
  expect(demandes.renommages).toEqual([{ ids: liste.map((titre) => titre.id), model: "artiste-titre", by_artist: false, dry_run: false }]);
  await expect(page.getByRole("button", { name: /^Ranger les/ })).toBeHidden();
  await expect(titres.getByRole("button", { name: "Ranger" })).toHaveCount(0);
});

test("un titre à relire s'ouvre, et un doublon possible se dit", async ({ page }) => {
  const liste = [nouveaute(1), ...autres()];
  const demandes = await arrivees(page, liste);
  await ouvrir(page);
  await page.getByRole("radio", { name: "Arrivées" }).click();

  const titres = page.getByRole("list", { name: "Titres arrivés" });
  const doublon = titres.getByRole("listitem").filter({ hasText: "groupe 22 – morceau 22" });
  await expect(doublon.getByText("Pas encore cherché en ligne.")).toBeVisible();
  await expect(doublon.getByText("Doublon possible : Rotation · ancien.mp3")).toBeVisible();

  const relire = titres.getByRole("listitem").filter({ hasText: "groupe 21 – morceau 21" }).first();
  await expect(relire.getByRole("button", { name: "Ranger" })).toHaveCount(0);
  await relire.getByRole("button", { name: "Relire" }).click();
  await relire.getByRole("button", { name: "Accepter" }).click();
  await expect(avis(page, /acceptée|écrite/)).toBeVisible();
  expect(demandes.decisions.at(-1)).toEqual({ accept: [121], refuse: [] });
  // Plus rien à relire : il est prêt à ranger.
  await expect(relire.getByRole("button", { name: "Ranger" })).toBeVisible();
});
