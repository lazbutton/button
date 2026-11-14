import type { Page, Route } from "@playwright/test";
import { verifierAccessibilite } from "./accessibilite.ts";
import { antenne, avis, expect, seConnecter, test } from "./banc.ts";

// Les étiquettes de la station (FON-74). Comme pour le tableau
// (banque-tableau.spec.ts), le parcours allume le rangement dans /account.json,
// et tient ici une petite bibliothèque, que les routes du tableau et des
// étiquettes lisent et changent comme le moteur
// (engine/radiotomate/services/station_tags.py) : une étiquette se cherche
// entière, « nuit » ne prend pas « minuit ».

type Titre = {
  id: number;
  title: string;
  artist: string;
  album: string;
  year: number | null;
  genre: string;
  famille: string;
  famille_label: string;
  etiquettes: string[];
  duration: number;
  zone: string;
  collection: string;
  path: string;
  missing: string[];
};
type Geste = { ids: number[]; add: string[]; remove: string[]; dry_run: boolean };

function titre(id: number, title: string, etiquettes: string[]): Titre {
  return {
    id,
    title,
    artist: "Orage",
    album: "Ciel",
    year: 2015,
    genre: "Jazz",
    famille: "jazz",
    famille_label: "Jazz",
    etiquettes,
    duration: 180 + id,
    zone: "rotation",
    collection: "rotation",
    path: `10-rotation/${id}.mp3`,
    missing: [],
  };
}

function facette(titres: Titre[]) {
  const comptes = new Map<string, number>();
  for (const entry of titres) {
    for (const tag of entry.etiquettes.length ? entry.etiquettes : [""]) comptes.set(tag, (comptes.get(tag) ?? 0) + 1);
  }
  return [...comptes]
    .map(([value, count]) => ({ value, label: value, count }))
    .sort((a, b) => Number(!a.value) - Number(!b.value) || a.value.localeCompare(b.value, "fr"));
}

/** Allume le rangement et les étiquettes ; `etiquettes: false` joue un moteur d'avant FON-74. */
async function banque(page: Page, { etiquettes = true } = {}): Promise<{ titres: Titre[]; gestes: Geste[] }> {
  const titres = [titre(1, "Comète", ["minuit"]), titre(2, "Brume", []), titre(3, "Dune", ["instrumental"])];
  const gestes: Geste[] = [];
  await page.route("**/account.json", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const reponse = await route.fetch();
    const compte = (await reponse.json()) as Record<string, unknown>;
    const features = { bank_tidy: true, title_edits: true, ...(etiquettes ? { station_tags: true } : {}) };
    await route.fulfill({ response: reponse, json: { ...compte, features } });
  });
  await page.route("**/media/titles.json*", async (route: Route) => {
    const q = new URL(route.request().url()).searchParams;
    const voulue = q.get("etiquette");
    const gardes = titres
      .filter((entry) => voulue === null || (voulue ? entry.etiquettes.includes(voulue) : !entry.etiquettes.length))
      .sort((a, b) => a.title.localeCompare(b.title, "fr"));
    const noms = (q.get("facets") ?? "").split(",").filter(Boolean);
    const facets = Object.fromEntries(noms.map((nom) => [nom, nom === "etiquette" ? facette(titres) : []]));
    await route.fulfill({
      json: { titles: gardes, total: titres.length, matched: gardes.length, offset: 0, limit: 100, sort: "title", order: "asc", facets },
    });
  });
  await page.route("**/media/titles/tags.json", async (route: Route) => {
    const geste = route.request().postDataJSON() as Geste;
    gestes.push(geste);
    let ecrits = 0;
    for (const id of geste.ids) {
      const entry = titres.find((item) => item.id === id);
      if (!entry) continue;
      const apres = [...new Set([...entry.etiquettes.filter((tag) => !geste.remove.includes(tag)), ...geste.add])].sort();
      if (apres.join("|") === entry.etiquettes.join("|")) continue;
      ecrits += 1;
      if (!geste.dry_run) entry.etiquettes = apres;
    }
    // Une sélection « Nuit » prend les titres étiquetés « nuit » : l'essai le dit.
    const nourrit = geste.dry_run && geste.add.includes("nuit");
    await route.fulfill({
      json: {
        dry_run: geste.dry_run,
        entry: geste.dry_run ? null : gestes.length,
        written: ecrits,
        waiting: [],
        kept: [],
        refused: [],
        unchanged: geste.ids.length - ecrits,
        selections: nourrit ? [{ id: 7, name: "Nuit", gained: ecrits, lost: 0 }] : [],
      },
    });
  });
  return { titres, gestes };
}

async function ouvrir(page: Page, adresse = "/sons?onglet=importer") {
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto(adresse);
}

const ligne = (page: Page, region: string, titre: string) =>
  page.getByRole("region", { name: region }).locator("tbody tr").filter({ hasText: titre });

test("poser « nuit » sur deux titres, ranger par étiquette, puis la retirer", async ({ page }) => {
  const { titres, gestes } = await banque(page);
  await ouvrir(page);
  const tout = page.getByRole("region", { name: "Toute la banque" });
  await expect(tout.getByRole("columnheader", { name: "Étiquettes" })).toBeVisible();
  await expect(ligne(page, "Toute la banque", "Comète").locator("td.c-etiquettes")).toHaveText("minuit");

  await ligne(page, "Toute la banque", "Brume").getByRole("checkbox").check();
  await ligne(page, "Toute la banque", "Comète").getByRole("checkbox").check();
  await tout.getByRole("toolbar", { name: "Sélection" }).getByRole("button", { name: "Étiquettes" }).click();

  const fenetre = page.getByRole("dialog", { name: "Étiquettes de 2 titres" });
  const champ = fenetre.getByRole("textbox", { name: "Nouvelle étiquette" });
  await expect(champ).toBeFocused();
  // Les étiquettes de la station se proposent, avec leur nombre de titres.
  const station = fenetre.getByRole("list", { name: "Étiquettes de la station" });
  await expect(station.getByRole("button", { name: "minuit 1" })).toBeVisible();
  // Une virgule ne passe pas : Beets y lirait la fin de la requête.
  await champ.fill("nuit,");
  await page.keyboard.press("Enter");
  await expect(fenetre.getByText("Une étiquette ne prend ni barre droite, ni virgule, ni guillemet : ils couperaient une sélection de titres.")).toBeVisible();
  await champ.fill("Nuit");
  await page.keyboard.press("Enter");
  await expect(fenetre.getByRole("list", { name: "Étiquettes à poser" })).toContainText("nuit");
  await expect(champ).toHaveValue("");
  await verifierAccessibilite(page, "fenêtre des étiquettes");

  // L'essai nomme la sélection que l'étiquette nourrit, avant d'écrire.
  await fenetre.getByRole("button", { name: "Appliquer", exact: true }).click();
  await expect(fenetre.getByText("« Nuit » gagne 2 titres.")).toBeVisible();
  expect(gestes).toEqual([{ ids: [2, 1], add: ["nuit"], remove: [], dry_run: true }]);
  await fenetre.getByRole("button", { name: "Appliquer à 2 titres" }).click();
  await expect(fenetre).toHaveCount(0);
  await expect(avis(page, "Étiquette « nuit » posée sur 2 titres.")).toBeVisible();
  expect(titres.find((entry) => entry.id === 1)?.etiquettes).toEqual(["minuit", "nuit"]);
  await expect(ligne(page, "Toute la banque", "Comète").locator("td.c-etiquettes")).toHaveText("minuit nuit");

  // Rangée par étiquette : « nuit » prend ses deux titres, et pas « minuit ».
  const colonne = page.getByRole("complementary", { name: "Ranger la banque" });
  await colonne.getByRole("combobox", { name: "Ranger par" }).click();
  await page.getByRole("option", { name: "Étiquette", exact: true }).click();
  await colonne.getByRole("option", { name: /^nuit/ }).click();
  await expect(page).toHaveURL(/ranger=etiquette&groupe=nuit/);
  const nuit = page.getByRole("region", { name: "nuit" });
  await expect(nuit.locator("tbody tr")).toHaveCount(2);

  // Retirer : par le menu d'une ligne, puis par la sélection.
  await nuit.getByRole("button", { name: "Actions pour Brume" }).click();
  await page.getByRole("menuitem", { name: "Étiquettes…" }).click();
  const seule = page.getByRole("dialog", { name: "Étiquettes de 1 titre" });
  await seule.getByRole("checkbox", { name: "nuit" }).check();
  await seule.getByRole("button", { name: "Appliquer", exact: true }).click();
  await expect(seule).toHaveCount(0);
  await expect(avis(page, "Étiquette « nuit » retirée de 1 titre.")).toBeVisible();
  expect(titres.find((entry) => entry.id === 2)?.etiquettes).toEqual([]);
  expect(gestes.at(-1)).toEqual({ ids: [2], add: [], remove: ["nuit"], dry_run: false });
});

test("une sélection par étiquette, depuis le tableau rangé par étiquette", async ({ page }) => {
  await banque(page);
  const composees: URLSearchParams[] = [];
  await page.route("**/media/selection.json*", async (route: Route) => {
    const filtres = new URL(route.request().url()).searchParams;
    composees.push(filtres);
    await route.fulfill({
      json: { query: `etiquettes:|${filtres.get("etiquette")}|`, count: 1, sample: [{ artist: "Orage", title: "Comète" }] },
    });
  });
  await ouvrir(page, "/sons?onglet=importer&ranger=etiquette&groupe=minuit");

  await page.getByRole("region", { name: "minuit" }).getByRole("link", { name: "Créer une sélection" }).click();
  const fenetre = page.getByRole("dialog", { name: "Nouvelle sélection de titres" });
  await expect(fenetre.getByRole("combobox", { name: "Étiquette" })).toContainText("minuit");
  await expect(fenetre.getByText("etiquettes:|minuit|")).toBeVisible();
  expect(composees.at(-1)?.toString()).toBe("etiquette=minuit");
  await expect(fenetre.getByRole("textbox", { name: "Nom" })).toHaveValue("Minuit");
});

test("un moteur d'avant les étiquettes : ni colonne, ni rangement, ni geste", async ({ page }) => {
  await banque(page, { etiquettes: false });
  await ouvrir(page);
  const tout = page.getByRole("region", { name: "Toute la banque" });
  await expect(tout.getByRole("button", { name: "Comète", exact: true })).toBeVisible();
  await expect(tout.getByRole("columnheader", { name: "Étiquettes" })).toHaveCount(0);

  await ligne(page, "Toute la banque", "Comète").getByRole("checkbox").check();
  const selection = tout.getByRole("toolbar", { name: "Sélection" });
  await expect(selection.getByRole("button", { name: "Modifier la fiche" })).toBeVisible();
  await expect(selection.getByRole("button", { name: "Étiquettes" })).toHaveCount(0);

  await page.getByRole("complementary", { name: "Ranger la banque" }).getByRole("combobox", { name: "Ranger par" }).click();
  await expect(page.getByRole("option", { name: "Album", exact: true })).toBeVisible();
  await expect(page.getByRole("option", { name: "Étiquette", exact: true })).toHaveCount(0);
  await page.keyboard.press("Escape");
  // La liste fermée, le reste de la page se lit de nouveau.
  await expect(page.getByRole("option", { name: "Album", exact: true })).toHaveCount(0);
});
