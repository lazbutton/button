import { readFileSync } from "node:fs";
import type { Page, Route } from "@playwright/test";
import { verifierAccessibilite } from "./accessibilite.ts";
import { antenne, avis, expect, seConnecter, test } from "./banc.ts";

// Relire par nature de changement (FON-79). Comme pour les fiches à relire
// (banque-relire.spec.ts), le parcours allume les interrupteurs dans /account.json,
// et tient ici les fiches. Ses groupes suivent la règle du moteur
// (engine/radiotomate/services/fiches_natures.py), réduite à ce que le parcours
// propose : une casse, ou un album ajouté, toujours sûrs et à relire.

const EXTRAIT = readFileSync(new URL("../../engine/tests/assets/formats/silence.mp3", import.meta.url));
const LABELS: Record<string, string> = {
  graphie: "La graphie : casse, accents, ponctuation",
  album: "Un album ajouté",
};

type Proposition = { id: number; field: string; before: string; value: string; level: string; state: string };
type Titre = { id: number; title: string; artist: string; level: string; propositions: Proposition[] };

const proposition = (id: number, field: string, before: string, value: string, level = "sûr"): Proposition => ({
  id,
  field,
  before,
  value,
  level,
  state: "proposée",
});

function natureOf(one: Proposition): string {
  if (one.state !== "proposée" || one.level !== "sûr") return "";
  if (one.before && one.before !== one.value && one.before.toLowerCase() === one.value.toLowerCase()) return "graphie";
  if (one.field === "album" && !one.before) return "album";
  return "";
}

function titreDe(titre: Titre, only?: (one: Proposition) => boolean) {
  return {
    id: titre.id,
    title: titre.title,
    artist: titre.artist,
    album: "",
    year: null,
    duration: 180,
    zone: "rotation",
    collection: "rotation",
    path: `10-rotation/${titre.id}.mp3`,
    status: "trouvé",
    level: titre.level,
    reasons: [],
    source: "Deezer",
    url: "",
    cover: null,
    propositions: titre.propositions
      .filter((one) => one.state === "proposée" && (!only || only(one)))
      .map((one) => ({ ...one, why: "", source: "Deezer", error: "" })),
  };
}

async function banc(page: Page, titres: Titre[]) {
  const decisions: Array<{ accept: number[]; refuse: number[] }> = [];
  await page.route("**/account.json", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const reponse = await route.fetch();
    const corps = (await reponse.json()) as Record<string, unknown>;
    await route.fulfill({ response: reponse, json: { ...corps, features: { bank_tidy: true, title_edits: true } } });
  });
  await page.route("**/autodj/beets/*", (route: Route) => route.fulfill({ contentType: "audio/mpeg", body: EXTRAIT }));
  const toutes = () => titres.flatMap((titre) => titre.propositions.map((one) => ({ titre, one })));
  await page.route("**/fiches.json*", async (route: Route) => {
    const q = new URL(route.request().url()).searchParams;
    const nature = q.get("nature");
    const offset = Number(q.get("offset") ?? 0);
    const garde = (one: Proposition) => one.state === "proposée" && (!nature || natureOf(one) === nature);
    const pris = titres.filter((titre) => titre.propositions.some(garde));
    await route.fulfill({
      json: {
        enabled: true,
        progress: { library: titres.length, searched: titres.length, remaining_hours: null },
        statuses: { trouvé: titres.length },
        levels: [{ value: "sûr", count: pris.length }],
        fields: [],
        states: [],
        banks: [{ value: "rotation", count: titres.length }],
        failures: [],
        titles: pris.slice(offset, offset + 50).map((titre) => titreDe(titre, garde)),
        total: pris.length,
        next: offset + 50 < pris.length ? offset + 50 : null,
      },
    });
  });
  await page.route("**/fiches/**", async (route: Route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/fiches/natures.json")) {
      const groupes = Object.keys(LABELS)
        .map((nature) => {
          const membres = toutes().filter(({ one }) => natureOf(one) === nature);
          return {
            nature,
            label: LABELS[nature],
            count: membres.length,
            titles: new Set(membres.map(({ titre }) => titre.id)).size,
            ids: membres.map(({ one }) => one.id),
            examples: membres.slice(0, 10).map(({ titre, one }) => ({
              id: one.id,
              beets_id: titre.id,
              title: titre.title,
              artist: titre.artist,
              field: one.field,
              before: one.before,
              value: one.value,
            })),
          };
        })
        .filter((groupe) => groupe.count > 0);
      return route.fulfill({ json: { groups: groupes } });
    }
    if (url.pathname.endsWith("/fiches/decisions.json")) {
      const corps = route.request().postDataJSON() as { accept?: number[]; refuse?: number[] };
      const accept = corps.accept ?? [];
      const refuse = corps.refuse ?? [];
      if (accept.length + refuse.length > 500) {
        return route.fulfill({ status: 400, json: { error: "validation_error", message: "Trop de propositions." } });
      }
      decisions.push({ accept, refuse });
      for (const { one } of toutes()) {
        if (accept.includes(one.id)) one.state = "écrite";
        if (refuse.includes(one.id)) one.state = "refusée";
      }
      return route.fulfill({
        json: { accepted: accept.length, refused: refuse.length, written: accept.length, waiting: [], failed: [], stale: 0, entry: 1 },
      });
    }
    const fiche = url.pathname.match(/fiches\/(\d+)\.json$/);
    if (fiche) {
      const titre = titres.find((one) => one.id === Number(fiche[1]));
      if (!titre) return route.fulfill({ status: 404, json: { error: "not_found", message: "Pas de fiche." } });
      const vue = titreDe(titre);
      return route.fulfill({
        json: {
          title: { ...vue, label: "", isrc: "" },
          fiche: {
            status: "trouvé",
            level: titre.level,
            reasons: [],
            source: "Deezer",
            url: "",
            error: "",
            attempts: 0,
            searched_at: "2026-11-15T10:00+01:00",
            next_at: null,
          },
          propositions: titre.propositions.map((one) => ({ ...one, why: "", source: "Deezer", error: "" })),
          evidence: null,
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
  return page.getByRole("region", { name: "Par nature de changement" });
}

test("un groupe de 600 corrections de casse s'accepte d'un geste, en deux lots, après dix exemples", async ({ page }) => {
  const titres: Titre[] = [
    ...Array.from({ length: 600 }, (_, index) => ({
      id: index + 1,
      title: `titre ${index + 1}`,
      artist: "Orage",
      level: "sûr",
      propositions: [proposition((index + 1) * 10, "title", `titre ${index + 1}`, `Titre ${index + 1}`)],
    })),
    // Une casse à revoir n'entre dans aucun groupe : elle se relit titre par titre.
    { id: 700, title: "brume", artist: "Orage", level: "à revoir", propositions: [proposition(7000, "title", "brume", "Brume", "à revoir")] },
    { id: 701, title: "Dune", artist: "Orage", level: "sûr", propositions: [proposition(7010, "album", "", "Sable")] },
  ];
  const { decisions } = await banc(page, titres);
  const natures = await ouvrir(page);

  const graphie = natures.getByRole("listitem").filter({ hasText: "La graphie" }).first();
  await expect(graphie).toContainText("600 propositions");
  await expect(natures.getByRole("listitem").filter({ hasText: "Un album ajouté" }).first()).toContainText("1 proposition");
  await graphie.getByText("10 exemples, pris au hasard").click();
  await expect(graphie.getByRole("list", { name: /^Exemples/ }).getByRole("listitem")).toHaveCount(10);
  await verifierAccessibilite(page, "les groupes par nature de changement");

  await graphie.getByRole("button", { name: "Accepter les 600 : La graphie : casse, accents, ponctuation" }).click();
  const fenetre = page.getByRole("dialog", { name: /La graphie.*accepter les 600 propositions/ });
  await expect(fenetre).toContainText("en 2 lots de 500 au plus");
  await expect(fenetre.getByRole("listitem")).toHaveCount(10);
  await verifierAccessibilite(page, "la confirmation d'un groupe");
  await fenetre.getByRole("button", { name: "Accepter les 600" }).click();

  await expect(avis(page, "600 propositions écrites.")).toBeVisible();
  expect(decisions.map((one) => one.accept.length)).toEqual([500, 100]);
  expect(decisions.flatMap((one) => one.accept)).not.toContain(7000);
  // Le groupe accepté s'en va ; l'album reste à accepter.
  await expect(natures.getByText("La graphie : casse, accents, ponctuation")).toHaveCount(0);
  await expect(natures).toContainText("Un album ajouté");
});

test("ouvrir un groupe le relit au clavier : ses seules propositions", async ({ page }) => {
  const titres: Titre[] = [
    {
      id: 1,
      title: "comète",
      artist: "Orage",
      level: "sûr",
      propositions: [proposition(10, "title", "comète", "Comète"), proposition(11, "album", "", "Ciel")],
    },
    { id: 2, title: "brume", artist: "Orage", level: "sûr", propositions: [proposition(20, "title", "brume", "Brume")] },
  ];
  const { decisions } = await banc(page, titres);
  const natures = await ouvrir(page);

  const bouton = natures.getByRole("button", { name: "Relire au clavier : La graphie : casse, accents, ponctuation" });
  await bouton.focus();
  await page.keyboard.press("Enter");
  const fenetre = page.getByRole("dialog", { name: "Relire au clavier" });
  await expect(fenetre.getByText("La graphie : casse, accents, ponctuation")).toBeVisible();
  await expect(fenetre.getByText("1 sur 2", { exact: true })).toBeVisible();
  // L'album proposé au même titre n'est pas du groupe : il ne se montre pas ici.
  await expect(fenetre.getByRole("table").getByRole("row")).toHaveCount(2);
  await expect(fenetre.getByRole("table")).not.toContainText("Album");

  await page.keyboard.press("a");
  await expect(fenetre.getByText("2 sur 2", { exact: true })).toBeVisible();
  await page.keyboard.press("a");
  await expect(fenetre.getByText("Tout est relu : 2 titres acceptés.", { exact: true })).toBeVisible();
  expect(decisions).toEqual([
    { accept: [10], refuse: [] },
    { accept: [20], refuse: [] },
  ]);
  await page.keyboard.press("Escape");
  await expect(fenetre).toHaveCount(0);
  // Le groupe relu s'en va ; l'album du premier titre reste à accepter.
  await expect(natures.getByText("La graphie : casse, accents, ponctuation")).toHaveCount(0);
  await expect(natures).toContainText("Un album ajouté");
});
