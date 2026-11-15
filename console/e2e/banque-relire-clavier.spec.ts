import { readFileSync } from "node:fs";
import type { Page, Route } from "@playwright/test";
import { verifierAccessibilite } from "./accessibilite.ts";
import { antenne, expect, seConnecter, test } from "./banc.ts";

// Relire au clavier (FON-78). Comme pour les fiches à relire (banque-relire.spec.ts),
// le parcours allume les interrupteurs dans /account.json, et tient ici les fiches
// que lisent et changent les routes, comme le moteur
// (engine/radiotomate/services/fiches_review.py et fiches_decisions.py) : la file
// se lit par pages de 30, A et R décident d'un titre entier, Z le remet à relire.
// L'extrait est un demi-seconde de silence.

const EXTRAIT = readFileSync(new URL("../../engine/tests/assets/formats/silence.mp3", import.meta.url));
const PAGE = 30;

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

function titre(id: number, title: string, level: string, champs: Array<[string, string, string]>): Titre {
  return {
    id,
    title,
    artist: "Orage",
    album: "",
    year: 0,
    duration: 180,
    zone: "rotation",
    collection: "rotation",
    path: `10-rotation/${id}.mp3`,
    status: "trouvé",
    level,
    reasons: level === "sûr" ? [] : ["durée : +14 s"],
    source: "Deezer",
    url: `https://www.deezer.com/track/${id}`,
    propositions: champs.map(([field, before, value], index) => ({
      id: id * 10 + index,
      field,
      before,
      value,
      level,
      why: "",
      source: "Deezer",
      state: "proposée",
      error: "",
    })),
  };
}

const cent = () =>
  Array.from({ length: 100 }, (_, index) =>
    titre(index + 1, `Titre ${String(index + 1).padStart(3, "0")}`, "sûr", [["year", "0", "1965"]]),
  );

async function banc(page: Page, titres: Titre[]) {
  const decisions: Array<{ accept: number[]; refuse: number[] }> = [];
  const annules: number[][] = [];
  const extraits: number[] = [];
  await page.route("**/account.json", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const reponse = await route.fetch();
    const corps = (await reponse.json()) as Record<string, unknown>;
    await route.fulfill({ response: reponse, json: { ...corps, features: { bank_tidy: true, title_edits: true } } });
  });
  await page.route("**/autodj/beets/*", async (route: Route) => {
    extraits.push(Number(new URL(route.request().url()).pathname.split("/").pop()));
    await route.fulfill({ contentType: "audio/mpeg", body: EXTRAIT });
  });
  const toutes = () => titres.flatMap((one) => one.propositions);
  await page.route("**/fiches.json*", async (route: Route) => {
    const q = new URL(route.request().url()).searchParams;
    const etat = q.get("state") ?? "proposée";
    const offset = Number(q.get("offset") ?? 0);
    const pris = titres.filter((one) => one.propositions.some((prop) => prop.state === etat));
    const page_ = pris.slice(offset, offset + PAGE);
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
        titles: page_.map((one) => ({ ...one, propositions: one.propositions.filter((prop) => prop.state === etat) })),
        total: pris.length,
        next: offset + PAGE < pris.length ? offset + PAGE : null,
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
      for (const one of toutes()) {
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
          entry: accept.length ? decisions.length : null,
        },
      });
    }
    if (url.pathname.endsWith("/fiches/decisions/annuler.json")) {
      const { ids } = route.request().postDataJSON() as { ids: number[] };
      annules.push(ids);
      let ecrites = 0;
      for (const one of toutes()) {
        if (!ids.includes(one.id)) continue;
        if (one.state === "écrite") ecrites += 1;
        one.state = "proposée";
      }
      return route.fulfill({
        json: { accepted: 0, refused: 0, written: ecrites, waiting: [], failed: [], stale: 0, entry: ecrites ? 900 : null },
      });
    }
    const fiche = url.pathname.match(/fiches\/(\d+)\.json$/);
    if (fiche) {
      const one = titres.find((item) => item.id === Number(fiche[1]));
      if (!one) return route.fulfill({ status: 404, json: { error: "not_found", message: "Pas de fiche." } });
      return route.fulfill({
        json: {
          title: { ...one, label: "", isrc: "" },
          fiche: {
            status: one.status,
            level: one.level,
            reasons: one.reasons,
            source: one.source,
            url: one.url,
            error: "",
            attempts: 0,
            searched_at: "2026-11-15T10:00+01:00",
            next_at: null,
          },
          propositions: one.propositions,
          evidence: {
            found_at: "Deezer",
            platform: "Deezer",
            url: one.url,
            title: one.title,
            artists: one.artist,
            album: "",
            duration: 182,
            genres: "",
            year_source: "Deezer",
            doubt: "",
          },
          listen: `/autodj/beets/${one.id}`,
        },
      });
    }
    return route.fallback();
  });
  return { decisions, annules, extraits };
}

async function ouvrir(page: Page) {
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer&vue=relire");
  const vue = page.getByRole("region", { name: "Fiches à relire" });
  const bouton = vue.getByRole("button", { name: "Relire au clavier" });
  // Sans souris : le bouton prend le focus, et Entrée l'ouvre.
  await bouton.focus();
  await page.keyboard.press("Enter");
  const fenetre = page.getByRole("dialog", { name: "Relire au clavier" });
  await expect(fenetre).toBeVisible();
  return { fenetre, bouton };
}

const annonce = (page: Page) => page.getByRole("dialog", { name: "Relire au clavier" }).getByRole("status");

test("cent propositions sûres se relisent au clavier, sans souris, et chaque geste s'annule", async ({ page }) => {
  // Cent gestes, chacun écrit puis relu : plus long qu'un parcours ordinaire.
  test.setTimeout(120_000);
  const titres = cent();
  const { decisions, annules } = await banc(page, titres);
  const { fenetre } = await ouvrir(page);

  await expect(fenetre.getByText("1 sur 100", { exact: true })).toBeVisible();
  await expect(fenetre.getByRole("heading", { name: "Titre 001" })).toBeVisible();
  for (let rang = 1; rang <= 100; rang += 1) {
    await page.keyboard.press("a");
    if (rang < 100) await expect(fenetre.getByText(`${rang + 1} sur 100`, { exact: true })).toBeVisible();
  }
  await expect(fenetre.getByText("Tout est relu : 100 titres acceptés.", { exact: true })).toBeVisible();
  // Un geste par titre, la file lue par pages de 30.
  expect(decisions).toHaveLength(100);
  expect(decisions.at(-1)).toEqual({ accept: [1000], refuse: [] });
  expect(titres.every((one) => one.propositions[0].state === "écrite")).toBe(true);

  // Z défait le dernier geste, puis celui d'avant : chaque titre revient à relire.
  await page.keyboard.press("z");
  await expect(fenetre.getByRole("heading", { name: "Titre 100" })).toBeVisible();
  await expect(annonce(page)).toContainText("Acceptation défaite : « Titre 100 ». Il est de nouveau à relire.");
  await page.keyboard.press("z");
  await expect(fenetre.getByRole("heading", { name: "Titre 099" })).toBeVisible();
  await expect(fenetre.getByText("99 sur 100", { exact: true })).toBeVisible();
  expect(annules).toEqual([[1000], [990]]);
  expect(titres[98].propositions[0].state).toBe("proposée");
  expect(titres[99].propositions[0].state).toBe("proposée");
});

test("A, Z, R, les flèches et Échap ; l'extrait part seul ; un titre à revoir s'accepte ouvert", async ({ page }) => {
  const titres = [
    titre(1, "Comète", "sûr", [
      ["year", "0", "1965"],
      ["label", "", "Ciel"],
    ]),
    titre(2, "Brume", "à revoir", [["album", "", "Nuages"]]),
    titre(3, "Dune", "rapproché", [["artist", "Orage", "Orage & Co"]]),
  ];
  const { decisions, annules, extraits } = await banc(page, titres);
  const { fenetre, bouton } = await ouvrir(page);

  // L'avant et l'après de chaque champ, côte à côte.
  const lignes = fenetre.getByRole("table").getByRole("row");
  await expect(lignes.filter({ hasText: "Année" })).toContainText("—1965");
  await expect(lignes.filter({ hasText: "Label" })).toContainText("—Ciel");
  await expect.poll(() => extraits).toContain(1);
  await verifierAccessibilite(page, "la relecture au clavier");

  await page.keyboard.press("a");
  await expect(fenetre.getByText("2 sur 3", { exact: true })).toBeVisible();
  await expect(annonce(page)).toContainText("« Comète » accepté. 2 propositions écrites. 2 sur 3 : « Brume ».");
  expect(decisions).toEqual([{ accept: [10, 11], refuse: [] }]);
  // L'extrait du titre précédent s'arrête, celui du suivant part.
  await expect.poll(() => extraits).toContain(2);

  await page.keyboard.press("z");
  await expect(fenetre.getByText("1 sur 3", { exact: true })).toBeVisible();
  expect(annules).toEqual([[10, 11]]);
  await expect(lignes.filter({ hasText: "Année" })).not.toContainText("Écrite");

  // Les flèches passent d'un titre à l'autre ; un titre à revoir se refuse ou s'accepte ouvert.
  await page.keyboard.press("ArrowRight");
  await expect(fenetre.getByRole("heading", { name: "Brume" })).toBeVisible();
  await page.keyboard.press("r");
  await expect(fenetre.getByRole("heading", { name: "Dune" })).toBeVisible();
  await page.keyboard.press("a");
  await expect(fenetre.getByText("Tout est relu : 1 titre accepté, 1 refusé.", { exact: true })).toBeVisible();
  expect(decisions.slice(1)).toEqual([
    { accept: [], refuse: [20] },
    { accept: [30], refuse: [] },
  ]);
  await page.keyboard.press("ArrowLeft");
  await expect(fenetre.getByRole("heading", { name: "Dune" })).toBeVisible();
  await expect(fenetre.getByRole("button", { name: "Accepter A" })).toBeDisabled();

  // Échap ferme, et le focus revient au bouton qui l'a ouverte.
  await page.keyboard.press("Escape");
  await expect(fenetre).toHaveCount(0);
  await expect(bouton).toBeFocused();
});

test("les flèches traversent la file, page après page, sans rien décider", async ({ page }) => {
  const titres = cent().slice(0, 70);
  const { decisions } = await banc(page, titres);
  const { fenetre } = await ouvrir(page);

  for (let rang = 2; rang <= 70; rang += 1) {
    await page.keyboard.press("ArrowRight");
    await expect(fenetre.getByText(`${rang} sur 70`, { exact: true })).toBeVisible();
  }
  await expect(fenetre.getByRole("heading", { name: "Titre 070" })).toBeVisible();
  await page.keyboard.press("r");
  await expect(fenetre.getByText("Tout est relu : 1 refusé.", { exact: true })).toBeVisible();
  expect(decisions).toEqual([{ accept: [], refuse: [700] }]);
  // Au premier titre, la flèche de gauche le dit, sans bouger.
  for (let rang = 70; rang >= 0; rang -= 1) await page.keyboard.press("ArrowLeft");
  await expect(fenetre.getByRole("heading", { name: "Titre 001" })).toBeVisible();
  await expect(fenetre.getByRole("status")).toContainText("C'est le premier titre.");
});
