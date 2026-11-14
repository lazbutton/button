import type { Page, Route } from "@playwright/test";
import { verifierAccessibilite } from "./accessibilite.ts";
import { antenne, avis, expect, seConnecter, test } from "./banc.ts";

// Le tableau de la banque (FON-64), derrière l'interrupteur général de « Ranger
// la banque ». Le moteur du banc le garde éteint, comme une station : le parcours
// l'allume dans la réponse de /account.json, et rend le tableau d'une
// bibliothèque tenue ici, filtrée et triée comme le moteur le fait
// (engine/radiotomate/services/bank_titles.py). Les collections viennent du faux
// catalogue : la rotation du banc.

type Titre = {
  id: number;
  title: string;
  artist: string;
  album: string;
  year: number | null;
  genre: string;
  famille: string;
  famille_label: string;
  duration: number | null;
  zone: string;
  collection: string;
  path: string;
  missing: string[];
};

const CHAMPS = ["title", "artist", "album", "year", "genre", "famille"] as const;

function titre(id: number, title: string, artist: string, album: string, year: number | null, famille = ""): Titre {
  const rotation = id % 2 === 1;
  const entry: Titre = {
    id,
    title,
    artist,
    album,
    year,
    genre: famille ? "Jazz" : "",
    famille,
    famille_label: famille ? famille[0].toUpperCase() + famille.slice(1) : "",
    duration: 180 + id,
    zone: rotation ? "rotation" : "collections",
    collection: rotation ? "rotation" : "nuit",
    path: rotation ? `10-rotation/${id}.mp3` : `20-archives/nuit/${id}.mp3`,
    missing: [],
  };
  entry.missing = CHAMPS.filter((name) => !entry[name]);
  return entry;
}

const BIBLIOTHEQUE = [
  titre(1, "Comète", "Orage", "Ciel", 2015, "jazz"),
  titre(2, "Été indien", "Orage", "Ciel", 2019, "jazz"),
  titre(3, "Brume", "Madame Orage", "", null),
  titre(4, "Dune", "Zéphyr", "Sable", 2021, "electro"),
];

const sansAccent = (text: string) =>
  text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();

type Facette = "collection" | "artist" | "famille" | "album" | "genre";

function facettes(nom: Facette) {
  const comptes = new Map<string, number>();
  for (const entry of BIBLIOTHEQUE) comptes.set(entry[nom], (comptes.get(entry[nom]) ?? 0) + 1);
  return [...comptes]
    // Comme le moteur : une famille se nomme en clair.
    .map(([value, count]) => ({
      value,
      label: nom === "famille" ? (BIBLIOTHEQUE.find((entry) => entry.famille === value)?.famille_label ?? value) : value,
      count,
    }))
    .sort((a, b) => Number(!a.value) - Number(!b.value) || a.label.localeCompare(b.label, "fr"));
}

/** Allume l'interrupteur et rend le tableau. Rend les adresses demandées, dans l'ordre. */
async function tableau(page: Page, statut = 200): Promise<URL[]> {
  const demandes: URL[] = [];
  await page.route("**/account.json", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const reponse = await route.fetch();
    const compte = (await reponse.json()) as Record<string, unknown>;
    await route.fulfill({ response: reponse, json: { ...compte, features: { bank_tidy: true } } });
  });
  await page.route("**/media/titles/*/plays.json", (route: Route) =>
    route.fulfill({
      json: {
        days: 90,
        count: 2,
        by_origin: { autodj: 1, bac: 0, agenda: 1, autre: 0 },
        recent: [
          { on_air: "2026-11-01T22:10+01:00", origin: "autodj", cart: null },
          { on_air: "2026-10-30T09:00+01:00", origin: "agenda", cart: null },
        ],
      },
    }),
  );
  await page.route("**/media/titles.json*", async (route: Route) => {
    const url = new URL(route.request().url());
    demandes.push(url);
    if (statut !== 200) return route.fulfill({ status: statut, json: { error: "not_found" } });
    const q = url.searchParams;
    const mots = sansAccent(q.get("q") ?? "").split(/\s+/).filter(Boolean);
    let gardes = BIBLIOTHEQUE.filter((entry) =>
      (["collection", "artist", "famille", "album"] as const).every(
        (nom) => !q.has(nom) || sansAccent(entry[nom]) === sansAccent(q.get(nom) ?? ""),
      ),
    ).filter((entry) => mots.every((mot) => sansAccent(`${entry.title} ${entry.artist} ${entry.album}`).includes(mot)));
    const tri = (q.get("sort") ?? "artist") as keyof Titre;
    gardes = [...gardes].sort((a, b) => String(a[tri] ?? "").localeCompare(String(b[tri] ?? ""), "fr"));
    if (q.get("order") === "desc") gardes.reverse();
    const noms = (q.get("facets") ?? "").split(",").filter(Boolean) as Facette[];
    await route.fulfill({
      json: {
        titles: gardes,
        total: BIBLIOTHEQUE.length,
        matched: gardes.length,
        offset: 0,
        limit: 100,
        sort: tri,
        order: q.get("order") ?? "asc",
        facets: Object.fromEntries(noms.map((nom) => [nom, facettes(nom)])),
      },
    });
  });
  return demandes;
}

test("toute la banque se range par artiste, se trie, et ouvre la fiche d'un titre", async ({ page }) => {
  const demandes = await tableau(page);
  await seConnecter(page, "admin");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer");

  const banque = page.getByRole("region", { name: "Toute la banque" });
  await expect(banque.getByRole("button", { name: "Comète", exact: true })).toBeVisible();
  await expect(banque.getByText("4 titres", { exact: true }).first()).toBeVisible();

  const colonne = page.getByRole("complementary", { name: "Ranger la banque" });
  await colonne.getByRole("combobox", { name: "Ranger par" }).click();
  await page.getByRole("option", { name: "Artiste", exact: true }).click();
  await colonne.getByRole("option", { name: /^Orage/ }).click();

  // Un artiste, pris seul : « Madame Orage » n'en est pas.
  const orage = page.getByRole("region", { name: "Orage" });
  await expect(orage.getByRole("button", { name: "Comète", exact: true })).toBeVisible();
  await expect(orage.getByRole("button", { name: "Brume", exact: true })).toHaveCount(0);
  expect(demandes.at(-1)?.searchParams.get("artist")).toBe("Orage");
  await expect(page).toHaveURL(/ranger=artist&groupe=Orage/);

  const annee = orage.getByRole("columnheader", { name: "Année" });
  await annee.getByRole("button", { name: "Année" }).click();
  await expect(annee).toHaveAttribute("aria-sort", "descending");
  await expect(orage.locator("tbody tr").first()).toContainText("Été indien");

  await orage.getByRole("button", { name: "Comète", exact: true }).click();
  const fiche = page.getByRole("complementary", { name: "Fiche de Comète" });
  await expect(fiche.getByText("Complète")).toBeVisible();
  await expect(fiche.getByText("10-rotation/1.mp3")).toBeVisible();
  const antenneDuTitre = fiche.getByRole("region", { name: "À l'antenne" });
  await expect(antenneDuTitre.getByText("Passé 2 fois en 90 jours")).toBeVisible();
  await expect(antenneDuTitre.getByText("Auto-DJ 1 · Agenda 1")).toBeVisible();
  await expect(antenneDuTitre.getByRole("list", { name: "Derniers passages" }).getByRole("listitem")).toHaveCount(2);
  // Un titre complet : son badge vert, dans la fiche et dans le tableau, se lit.
  await verifierAccessibilite(page, "fiche d'un titre complet");
  await page.keyboard.press("Escape");
  await expect(fiche).toHaveCount(0);
  await expect(orage.getByRole("button", { name: "Comète", exact: true })).toBeFocused();

  // Les groupes vides se nomment : un titre sans album.
  await colonne.getByRole("combobox", { name: "Ranger par" }).click();
  await page.getByRole("option", { name: "Album", exact: true }).click();
  await colonne.getByRole("option", { name: /^Sans album/ }).click();
  await expect(page.getByRole("region", { name: "Sans album" }).getByRole("button", { name: "Brume", exact: true })).toBeVisible();
  expect(demandes.at(-1)?.search).toContain("album=&");
});

test("rangée par collection, la rotation garde ses gestes", async ({ page }) => {
  await tableau(page);
  await seConnecter(page, "admin");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer&groupe=rotation");

  const rotation = page.getByRole("region", { name: "Rotation" });
  await expect(rotation.getByRole("button", { name: "Ajouter des titres" })).toBeVisible();
  await rotation.getByRole("checkbox", { name: "Sélectionner Comète" }).click();
  const selection = rotation.getByRole("toolbar", { name: "Sélection" });
  await expect(selection.getByRole("button", { name: "Retirer" })).toBeVisible();
  await expect(selection.getByRole("button", { name: "Déplacer" })).toBeVisible();
});

test("sur téléphone, la liste des groupes, puis le tableau, puis la fiche", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await tableau(page);
  await seConnecter(page, "admin");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer&ranger=famille");

  const colonne = page.getByRole("complementary", { name: "Ranger la banque" });
  await colonne.getByRole("option", { name: /^Sans famille/ }).click();
  const sansFamille = page.getByRole("region", { name: "Sans famille" });
  await expect(sansFamille.getByRole("button", { name: "Brume", exact: true })).toBeVisible();
  await expect(colonne).toBeHidden();
  await sansFamille.getByRole("button", { name: "Brume", exact: true }).click();
  const fiche = page.getByRole("complementary", { name: "Fiche de Brume" });
  await expect(fiche.getByText("4 champs vides")).toBeVisible();
  await fiche.getByRole("button", { name: "Fermer la fiche" }).click();
  await sansFamille.getByRole("button", { name: /Retour à la liste/ }).click();
  await expect(colonne).toBeVisible();
});

test("devant un moteur qui n'a pas le tableau, la console demande de le mettre à jour", async ({ page }) => {
  await tableau(page, 404);
  await seConnecter(page, "admin");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer");
  await expect(page.getByText("Mets à jour le moteur")).toBeVisible();
});

/** Les vues gardées, tenues ici comme le moteur les tient (FON-65). Rend les corps reçus. */
async function vues(page: Page): Promise<Array<Record<string, unknown>>> {
  const recus: Array<Record<string, unknown>> = [];
  const gardees: Array<{ id: number; name: string; state: unknown; modified: string }> = [];
  await page.route("**/media/views**", async (route: Route) => {
    const requete = route.request();
    if (requete.method() === "GET") return route.fulfill({ json: { views: gardees } });
    const corps = requete.postDataJSON() as Record<string, unknown>;
    recus.push(corps);
    if (requete.method() === "POST") {
      const vue = { id: gardees.length + 1, name: String(corps.name), state: corps.state, modified: "2026-11-14T17:00+01:00" };
      gardees.push(vue);
      return route.fulfill({ status: 201, json: { view: vue } });
    }
    return route.fulfill({ status: 404, json: { error: "not_found" } });
  });
  return recus;
}

test("choisir ses colonnes, garder la vue sous un nom, puis la rouvrir", async ({ page }) => {
  await tableau(page);
  const recus = await vues(page);
  await seConnecter(page, "admin");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer&ranger=famille&groupe=jazz");

  const jazz = page.getByRole("region", { name: "Jazz" });
  await jazz.getByRole("button", { name: "Colonnes" }).click();
  const colonnes = page.getByRole("dialog", { name: "Colonnes du tableau" });
  await colonnes.getByRole("checkbox", { name: "Album" }).click();
  // Au clavier : l'année monte de trois places, devant l'artiste.
  for (let fois = 0; fois < 3; fois++) await colonnes.getByRole("button", { name: "Monter Année" }).click();
  await page.keyboard.press("Escape");
  await expect(jazz.getByRole("columnheader", { name: "Album" })).toHaveCount(0);
  // L'année vient juste après le titre (devant, la case à cocher et l'écoute).
  const entetes = jazz.getByRole("columnheader");
  await expect(entetes.filter({ hasText: /^Titre$/ }).locator("xpath=following-sibling::th[1]")).toHaveText("Année");

  await jazz.getByRole("button", { name: "Vues" }).click();
  await page.getByRole("menuitem", { name: "Garder cette vue…" }).click();
  await page.getByRole("textbox", { name: "Nom" }).fill("Jazz à relire");
  await page.getByRole("button", { name: "Garder la vue" }).click();
  await expect(jazz.getByRole("button", { name: "Jazz à relire" })).toBeVisible();
  expect(recus[0]).toEqual({
    name: "Jazz à relire",
    state: {
      ranking: "famille",
      group: "jazz",
      q: "",
      sort: "artist",
      order: "asc",
      columns: ["title", "year", "artist", "famille", "genre", "duration", "fiche"],
    },
  });

  // Ailleurs dans la banque, la vue se rouvre d'un clic.
  await page.goto("/sons?onglet=importer&ranger=album");
  const banque = page.getByRole("region", { name: "Toute la banque" });
  await banque.getByRole("button", { name: "Vues" }).click();
  await page.getByRole("menuitem", { name: "Jazz à relire" }).click();
  await expect(page.getByRole("region", { name: "Jazz" }).getByRole("columnheader", { name: "Album" })).toHaveCount(0);
  await expect(page).toHaveURL(/ranger=famille&groupe=jazz/);
});

test("composer une sélection par filtres, depuis le tableau rangé par famille", async ({ page }) => {
  await tableau(page);
  const composees: URLSearchParams[] = [];
  await page.route("**/media/selection.json*", async (route: Route) => {
    const filtres = new URL(route.request().url()).searchParams;
    composees.push(filtres);
    const depuis = Number(filtres.get("year_from") ?? 0);
    const pris = BIBLIOTHEQUE.filter(
      (entry) => entry.famille === filtres.get("famille") && (entry.year ?? 0) >= depuis,
    );
    const requete = ["famille:=jazz", depuis ? `year:${depuis}..` : ""].filter(Boolean).join(" ");
    await route.fulfill({
      json: { query: requete, count: pris.length, sample: pris.map(({ artist, title }) => ({ artist, title })) },
    });
  });
  const creees: Array<Record<string, unknown>> = [];
  await page.route("**/autodj/categories.json", async (route: Route) => {
    if (route.request().method() !== "POST") return route.fallback();
    creees.push(route.request().postDataJSON() as Record<string, unknown>);
    await route.fulfill({ status: 201, json: { category: { id: 99 } } });
  });
  await seConnecter(page, "admin");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer&ranger=famille&groupe=jazz");

  await page.getByRole("region", { name: "Jazz" }).getByRole("link", { name: "Créer une sélection" }).click();
  const fenetre = page.getByRole("dialog", { name: "Nouvelle sélection de titres" });
  await expect(fenetre.getByRole("radio", { name: "Par filtres" })).toHaveAttribute("aria-checked", "true");
  await expect(fenetre.getByRole("combobox", { name: "Famille" })).toContainText("Jazz");
  await expect(fenetre.getByRole("textbox", { name: "Nom" })).toHaveValue("Jazz");
  await expect(fenetre.getByText("2 titres")).toBeVisible();

  await fenetre.getByRole("textbox", { name: "Depuis" }).fill("2016");
  await expect(fenetre.getByText("1 titre", { exact: true })).toBeVisible();
  await expect(fenetre.getByText("year:2016..")).toBeVisible();
  expect(composees.at(-1)?.toString()).toBe("famille=jazz&year_from=2016");
  await expect(fenetre.getByRole("textbox", { name: "Nom" })).toHaveValue("Jazz depuis 2016");

  // « Écrire la requête à la main » reprend la requête composée.
  await fenetre.getByRole("radio", { name: "Écrire la requête à la main" }).click();
  await expect(fenetre.getByRole("textbox", { name: "Requête", exact: true })).toHaveValue("famille:=jazz year:2016..");
  await fenetre.getByRole("radio", { name: "Par filtres" }).click();
  await fenetre.getByRole("button", { name: "Créer la sélection" }).click();
  await expect.poll(() => creees.length).toBe(1);
  expect(creees[0]).toEqual({ name: "Jazz depuis 2016", query: "famille:=jazz year:2016..", empty_query: "" });
});

/** Les ajouts de titres de la banque à un bac (FON-69) : rend le corps reçu, et le bac tel qu'il était, un son de plus. */
async function ajoutsAuBac(page: Page): Promise<Array<Record<string, unknown>>> {
  const recus: Array<Record<string, unknown>> = [];
  await page.route("**/carts/*/sounds.json", async (route: Route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const corps = route.request().postDataJSON() as Record<string, unknown>;
    recus.push(corps);
    const id = Number(new URL(route.request().url()).pathname.split("/").at(-2));
    const reponse = await page.request.get("/carts.json");
    const bac = ((await reponse.json()) as { carts: Array<Record<string, unknown> & { id: number; sounds: unknown[] }> }).carts.find(
      (cart) => cart.id === id,
    );
    if (!bac) return route.fulfill({ status: 404, json: { error: "not_found" } });
    const ajoutes = (corps.titles as string[]).map((path, rang) => ({
      id: 9000 + rang,
      rank: bac.sounds.length + rang + 1,
      title: `Orage - ${path}`,
      duration: 200,
      active: true,
      available: false,
      gain: null,
      peak: null,
      last_played: null,
      uploader: "admin",
      path,
      borrowed: true,
      missing: false,
    }));
    await route.fulfill({ status: 201, json: { cart: { ...bac, sounds: [...bac.sounds, ...ajoutes] } } });
  });
  return recus;
}

test("ajouter des titres du tableau à un bac, sans copie", async ({ page }) => {
  await tableau(page);
  const recus = await ajoutsAuBac(page);
  await seConnecter(page, "admin");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer&ranger=artist&groupe=Orage");

  const orage = page.getByRole("region", { name: "Orage" });
  await orage.getByRole("checkbox", { name: "Sélectionner Comète" }).click();
  await orage.getByRole("checkbox", { name: "Sélectionner Été indien" }).click();
  await orage.getByRole("toolbar", { name: "Sélection" }).getByRole("button", { name: "Ajouter à un bac" }).click();
  const fenetre = page.getByRole("dialog", { name: "Ajouter 2 titres à un bac" });
  await expect(fenetre.getByText("un bac ouvert dans Dropbox ne les voit pas")).toBeVisible();
  await fenetre.getByRole("combobox", { name: "Bac" }).click();
  await page.getByRole("option", { name: /Musique de démo/ }).click();
  await fenetre.getByRole("button", { name: "Ajouter à « Musique de démo »" }).click();
  await expect(page.getByRole("status").filter({ hasText: "2 titres de la banque ajoutés au bac « Musique de démo », sans copie." })).toBeVisible();
  expect(recus).toEqual([{ titles: ["10-rotation/1.mp3", "20-archives/nuit/2.mp3"] }]);
});

test("un bac prend des titres de la banque, et dit qu'ils viennent de la banque", async ({ page }) => {
  await tableau(page);
  const recus = await ajoutsAuBac(page);
  await seConnecter(page, "admin");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons");
  await page.getByRole("option", { name: /Musique de démo/ }).click();
  const bac = page.getByRole("region", { name: "Musique de démo" });

  await bac.getByRole("button", { name: /^Ajouter/ }).click();
  await page.getByRole("menuitem", { name: /Titres de la banque/ }).click();
  const fenetre = page.getByRole("dialog", { name: "Titres de la banque pour « Musique de démo »" });
  await fenetre.getByRole("textbox", { name: "Chercher dans la banque" }).fill("dune");
  await expect(fenetre.getByRole("checkbox")).toHaveCount(1);
  await fenetre.getByRole("checkbox").click();
  await fenetre.getByRole("button", { name: "Ajouter 1 titre" }).click();
  await expect(fenetre).toHaveCount(0);
  expect(recus).toEqual([{ titles: ["20-archives/nuit/4.mp3"] }]);
  await expect(bac.getByText("Banque", { exact: true })).toBeVisible();
});

test("un titre glissé sur la zone des bacs s'y ajoute, sans copie", async ({ page }) => {
  await tableau(page);
  const recus = await ajoutsAuBac(page);
  await seConnecter(page, "admin");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons?onglet=importer&ranger=artist&groupe=Orage");
  const orage = page.getByRole("region", { name: "Orage" });

  // La zone n'existe qu'une fois le glisser commencé : la souris le mène.
  await orage.locator("tbody tr").filter({ hasText: "Comète" }).hover();
  await page.mouse.down();
  await page.mouse.move(400, 500, { steps: 5 });
  const zone = orage.getByText(/Déposer ici pour ajouter ce titre à un bac/);
  await expect(zone).toBeVisible();
  await zone.hover();
  await page.mouse.up();

  const fenetre = page.getByRole("dialog", { name: "Ajouter ce titre à un bac" });
  await fenetre.getByRole("combobox", { name: "Bac" }).click();
  await page.getByRole("option", { name: /Musique de démo/ }).click();
  await fenetre.getByRole("button", { name: "Ajouter à « Musique de démo »" }).click();
  await expect(avis(page, "1 titre de la banque ajouté au bac « Musique de démo », sans copie.")).toBeVisible();
  expect(recus).toEqual([{ titles: ["10-rotation/1.mp3"] }]);
});
