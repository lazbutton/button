import type { Page, Route } from "@playwright/test";
import { verifierAccessibilite } from "./accessibilite.ts";
import { antenne, avis, expect, seConnecter, test } from "./banc.ts";

// Les fiches à relire : accepter, refuser, revenir (FON-26, FON-27). Le moteur du
// banc n'a ni bibliothèque Beets, ni recherche des fiches, ni le rangement allumé :
// le parcours allume les interrupteurs dans /account.json, et tient ici les fiches
// que lisent et changent les routes de la page, comme le moteur
// (engine/radiotomate/services/fiches_decisions.py).

type Proposition = {
  id: number;
  field: string;
  before: string;
  value: string;
  level: string;
  why: string;
  source: string;
  state: string;
  error: string;
};
type Titre = {
  id: number;
  title: string;
  artist: string;
  album: string;
  year: number;
  duration: number;
  zone: string;
  collection: string;
  path: string;
  status: string;
  level: string;
  reasons: string[];
  source: string;
  url: string;
  propositions: Proposition[];
};

const proposition = (id: number, field: string, before: string, value: string, level = "sûr"): Proposition => ({
  id,
  field,
  before,
  value,
  level,
  why: "",
  source: "Deezer",
  state: "proposée",
  error: "",
});

function bibliotheque(): Titre[] {
  const titre = (id: number, title: string, artist: string, level: string, propositions: Proposition[]): Titre => ({
    id,
    title,
    artist,
    album: "",
    year: 0,
    duration: 180,
    zone: "rotation",
    collection: "rotation",
    path: `10-rotation/${id}.mp3`,
    status: "trouvé",
    level,
    reasons: level === "à revoir" ? ["durée : +14 s"] : [],
    source: "Deezer",
    url: `https://www.deezer.com/track/${id}`,
    propositions,
  });
  return [
    titre(1, "Comète", "Orage", "sûr", [proposition(11, "year", "0", "1965"), proposition(12, "label", "", "Ciel")]),
    titre(2, "Brume", "Orage", "à revoir", [proposition(21, "album", "", "Nuages", "à revoir")]),
  ];
}

async function banc(page: Page, ecrire = true) {
  const titres = bibliotheque();
  const decisions: Array<{ accept: number[]; refuse: number[] }> = [];
  await page.route("**/account.json", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const reponse = await route.fetch();
    const corps = (await reponse.json()) as Record<string, unknown>;
    await route.fulfill({ response: reponse, json: { ...corps, features: { bank_tidy: true, title_edits: ecrire } } });
  });
  const toutes = () => titres.flatMap((titre) => titre.propositions.map((one) => ({ titre, one })));
  await page.route("**/fiches.json*", async (route: Route) => {
    const attend = titres.filter((titre) => titre.propositions.some((one) => one.state === "proposée"));
    await route.fulfill({
      json: {
        enabled: true,
        progress: { library: 2, searched: 2, remaining_hours: null },
        statuses: { trouvé: 2 },
        levels: [
          { value: "sûr", count: 1 },
          { value: "à revoir", count: 1 },
        ],
        fields: [],
        states: [],
        banks: [{ value: "rotation", count: 2 }],
        failures: [],
        titles: attend.map((titre) => ({
          ...titre,
          propositions: titre.propositions.filter((one) => one.state === "proposée"),
        })),
        total: attend.length,
        next: null,
      },
    });
  });
  await page.route("**/fiches/**", async (route: Route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/fiches/decisions.json")) {
      const corps = route.request().postDataJSON() as { accept?: number[]; refuse?: number[] };
      const accept = corps.accept ?? [];
      const refuse = corps.refuse ?? [];
      decisions.push({ accept, refuse });
      for (const { one } of toutes()) {
        if (accept.includes(one.id)) one.state = "écrite";
        if (refuse.includes(one.id)) one.state = "refusée";
      }
      return route.fulfill({
        json: {
          accepted: accept.length,
          refused: refuse.length,
          written: accept.length,
          waiting: [],
          failed: [],
          stale: 0,
          entry: accept.length ? 7 : null,
        },
      });
    }
    const revenir = url.pathname.match(/propositions\/(\d+)\/revenir\.json$/);
    if (revenir) {
      const trouve = toutes().find(({ one }) => one.id === Number(revenir[1]));
      if (trouve) trouve.one.state = "revenue";
      return route.fulfill({
        json: { accepted: 0, refused: 0, written: 1, waiting: [], failed: [], stale: 0, entry: 8 },
      });
    }
    const fiche = url.pathname.match(/fiches\/(\d+)\.json$/);
    if (fiche) {
      const titre = titres.find((one) => one.id === Number(fiche[1]));
      if (!titre) return route.fulfill({ status: 404, json: { error: "not_found", message: "Pas de fiche." } });
      return route.fulfill({
        json: {
          title: { ...titre, label: "", isrc: "" },
          fiche: {
            status: titre.status,
            level: titre.level,
            reasons: titre.reasons,
            source: titre.source,
            url: titre.url,
            error: "",
            attempts: 0,
            searched_at: "2026-11-14T22:41+01:00",
            next_at: null,
          },
          propositions: titre.propositions,
          evidence: {
            found_at: "Deezer",
            platform: "Deezer",
            url: titre.url,
            title: titre.title,
            artists: titre.artist,
            album: "Nuages",
            duration: 182,
            genres: "",
            year_source: "Deezer",
            doubt: "",
          },
          listen: `/autodj/beets/${titre.id}`,
        },
      });
    }
    return route.fallback();
  });
  return { decisions };
}

async function ouvrir(page: Page) {
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer&vue=relire");
  return page.getByRole("region", { name: "Fiches à relire" });
}

test("une proposition acceptée s'écrit, puis revient à la valeur d'avant", async ({ page }) => {
  const { decisions } = await banc(page);
  const vue = await ouvrir(page);

  await vue.getByRole("button", { name: /^Comète/ }).click();
  const fiche = vue.locator("li.fiches-title").filter({ hasText: "Comète" });
  await expect(fiche.getByText("Écouter sur Deezer")).toBeVisible();

  await fiche.getByRole("button", { name: "Accepter Année" }).click();
  await expect(avis(page, "1 proposition écrite.")).toBeVisible();
  expect(decisions).toEqual([{ accept: [11], refuse: [] }]);
  const annee = fiche.locator("li.fiches-prop").filter({ hasText: "Année" });
  await expect(annee.getByText("Écrite")).toBeVisible();

  await annee.getByRole("button", { name: "Revenir à la valeur d'avant de Année" }).click();
  await expect(avis(page, "Année : la valeur d'avant est revenue.")).toBeVisible();
  await expect(annee.getByText("Revenue")).toBeVisible();

  // Le reste du titre se refuse d'un geste.
  await fiche.getByRole("button", { name: "Refuser la proposition de Comète" }).click();
  await expect(avis(page, "1 proposition refusée.")).toBeVisible();
  expect(decisions.at(-1)).toEqual({ accept: [], refuse: [12] });
  await verifierAccessibilite(page, "la fiche dépliée d'un titre à relire");
});

test("les propositions sûres affichées s'acceptent en lot, après confirmation", async ({ page }) => {
  const { decisions } = await banc(page);
  const vue = await ouvrir(page);

  await vue.getByRole("button", { name: "Accepter les 2 propositions sûres affichées" }).click();
  const fenetre = page.getByRole("alertdialog").or(page.getByRole("dialog"));
  await expect(fenetre.getByText(/Elles s'écrivent dans les fichiers de 1 titre/)).toBeVisible();
  await fenetre.getByRole("button", { name: "Accepter et écrire" }).click();
  await expect(avis(page, "2 propositions écrites.")).toBeVisible();
  // Le titre à revoir n'entre pas dans le lot : il s'accepte seul, une fois ouvert.
  expect(decisions).toEqual([{ accept: [11, 12], refuse: [] }]);
  await expect(vue.getByRole("button", { name: /^Brume/ })).toBeVisible();
});

test("la correction des fiches coupée, on relit et on refuse sans rien accepter", async ({ page }) => {
  await banc(page, false);
  const vue = await ouvrir(page);

  await expect(vue.getByText(/La correction des fiches est coupée/)).toBeVisible();
  await expect(vue.getByRole("button", { name: /Accepter les/ })).toHaveCount(0);
  await vue.getByRole("button", { name: /^Brume/ }).click();
  const fiche = vue.locator("li.fiches-title").filter({ hasText: "Brume" });
  await expect(fiche.getByRole("button", { name: /^Accepter/ })).toHaveCount(0);
  await expect(fiche.getByRole("button", { name: "Refuser Album" })).toBeVisible();
});
