import type { Page, Route } from "@playwright/test";
import type { Rundown, RundownItem } from "../src/api/types.ts";
import { alerte, antenne, avis, expect, seConnecter, test } from "./banc.ts";

// La page Conducteur : ce qui va passer, lu dans les mots de la console, les
// lignes à réparer, un retrait, et un conducteur qui ne répond plus. Une ligne
// sans son et un retrait sont simulés par page.route devant le moteur de démo :
// son horloge trouve toujours ses sons, et un retrait ne change pas le moteur
// que les autres parcours partagent.

const CONDUCTEUR = "**/autodj/conducteur.json*";
// Un retrait se pose sur la file, une ligne du pupitre et un retrait s'effacent.
const RETRAIT = "**/autodj/conducteur/items.json";
const LIGNE = "**/autodj/conducteur/items/*.json";
const deroule = (page: Page) => page.getByRole("list", { name: "Déroulé du conducteur" });
const lignes = (page: Page) => deroule(page).getByRole("listitem");
const retraits = (page: Page) => page.getByRole("button", { name: /^Retirer .+ du conducteur$/ });

async function ouvrir(page: Page, role: "animateur" | "programmateur"): Promise<void> {
  await seConnecter(page, role);
  // La session ouverte, et pas avant : partir plus tôt couperait la connexion.
  await expect(antenne(page)).toBeVisible();
  await page.goto("/conducteur");
  await expect(lignes(page).first()).toBeVisible();
}

/**
 * Le conducteur du moteur, où une ligne de l'horloge à venir n'a plus de son :
 * son bac est introuvable. La même ligne d'une lecture à l'autre, choisie à la
 * première.
 */
function avecUnBacVide(): (route: Route) => Promise<void> {
  let choisie: string | undefined;
  return async (route) => {
    const reponse = await route.fetch();
    const conducteur = (await reponse.json()) as Rundown;
    const apres = Date.now() + 60_000;
    choisie ??= conducteur.items.find((item) => item.origin === "clock" && Date.parse(item.at) > apres)?.id;
    conducteur.items = conducteur.items.map((item): RundownItem => {
      if (!choisie || item.id !== choisie) return item;
      const { title: _title, artist: _artist, category: _category, ...ligne } = item;
      return {
        ...ligne,
        kind: "jingle",
        status: "manquant",
        status_code: "failed",
        reason: "cart introuvable",
        resource: "Bac fantôme",
        cart: "Bac fantôme",
      };
    });
    await route.fulfill({ response: reponse, json: conducteur });
  };
}

test("le conducteur se lit dans les mots de la console", async ({ page }) => {
  await ouvrir(page, "animateur");
  const conducteur = page.getByRole("main");
  await expect(conducteur.getByText("Heure type", { exact: true })).toBeVisible();
  await expect(conducteur.getByText("Horloge des parcours", { exact: true })).toBeVisible();
  // Une ligne à l'antenne ; « prévu » et « séquentiel » ne se disent plus sur chaque ligne.
  await expect(lignes(page).filter({ hasText: "À l’antenne" })).toHaveCount(1);
  await expect(deroule(page)).not.toContainText("prévu");
  await expect(deroule(page)).not.toContainText("séquentiel");
  // L'animateur lit le conducteur sans le changer.
  await expect(retraits(page)).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Horloge des parcours" })).toHaveCount(0);
});

test("une ligne sans son : le bandeau la compte, et mène à son bouton « Réparer »", async ({ page }) => {
  await page.route(CONDUCTEUR, avecUnBacVide());
  await ouvrir(page, "programmateur");
  await expect(page.getByText(/^1 ligne à réparer d’ici \d{2}:\d{2}\.$/)).toBeVisible();

  await page.getByRole("button", { name: "Voir la ligne" }).click();
  const reparer = page.getByRole("button", { name: "Réparer Bac fantôme" });
  await expect(reparer).toBeFocused();
  await expect(lignes(page).filter({ has: reparer })).toContainText("bac introuvable ou sans son");

  await page.keyboard.press("Enter");
  const dialogue = page.getByRole("dialog", { name: "Réparer « Bac fantôme »" });
  await expect(dialogue).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialogue).toBeHidden();
  // Fermé, le dialogue rend le focus au bouton qui l'a ouvert.
  await expect(reparer).toBeFocused();
});

test("l’animateur voit la ligne à réparer, et qui peut la réparer", async ({ page }) => {
  await page.route(CONDUCTEUR, avecUnBacVide());
  await ouvrir(page, "animateur");
  await expect(page.getByText("Un programmateur peut la réparer ici.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Réparer / })).toHaveCount(0);

  await page.getByRole("button", { name: "Voir la ligne" }).click();
  await expect(lignes(page).filter({ hasText: "Bac fantôme" })).toBeFocused();
});

test("retirer une ligne de l’horloge au clavier : un retrait, qu’« Annuler » lève", async ({ page }) => {
  // Le retrait ne va pas jusqu'au moteur : la page répond comme lui. Elle sert la
  // file lue la première fois, figée, pour que les heures ne glissent pas pendant
  // le geste. Le retrait posé cache sa ligne, et son effacement, « Annuler », la rend.
  const RETRAIT_POSE = "retrait-du-parcours";
  let figee: Rundown | undefined;
  let masquee: string | undefined;
  const effaces: string[] = [];
  const servie = (): Rundown => {
    if (!figee) throw new Error("La file n'a pas encore été lue.");
    return { ...figee, items: figee.items.filter((item) => !masquee || item.id !== masquee) };
  };
  await page.route(CONDUCTEUR, async (route) => {
    const reponse = await route.fetch();
    if (!reponse.ok()) return route.fulfill({ response: reponse });
    figee ??= (await reponse.json()) as Rundown;
    await route.fulfill({ response: reponse, json: servie() });
  });
  await page.route(RETRAIT, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    masquee = (route.request().postDataJSON() as { suppress_id?: string }).suppress_id;
    await route.fulfill({ json: { ...servie(), desk_item: { id: RETRAIT_POSE, origin: "desk" } } });
  });
  await page.route(LIGNE, async (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    const nom = new URL(route.request().url()).pathname.split("/").pop() ?? "";
    const efface = decodeURIComponent(nom.replace(/\.json$/, ""));
    effaces.push(efface);
    if (efface === RETRAIT_POSE) masquee = undefined;
    await route.fulfill({ json: servie() });
  });
  await ouvrir(page, "programmateur");

  // La première ligne de l'horloge à retirer à plus d'une minute, qui reste à venir
  // pendant le geste, et que son heure exacte désigne seule. La page ne dit pas
  // d'où vient une ligne : le parcours le lit dans la file servie. Les boutons
  // « Retirer » n'arrivent qu'avec le rôle du compte, lu après la file.
  await expect(retraits(page).first()).toBeVisible();
  const apres = Date.now() + 60_000;
  const heures = await lignes(page)
    .filter({ has: retraits(page) })
    .getByRole("time")
    .evaluateAll((balises) => balises.map((balise) => balise.getAttribute("datetime") ?? ""));
  const visee = heures
    .filter((at) => Date.parse(at) > apres)
    .map((at) => servie().items.filter((item) => item.at === at))
    .find((memes) => memes.length === 1 && memes[0].origin === "clock" && memes[0].id)?.[0];
  if (!visee?.id) throw new Error(`Aucune ligne de l'horloge à retirer parmi : ${heures.join(", ")}.`);
  const heure = deroule(page).locator(`time[datetime="${visee.at}"]`);
  // Le localisateur de `has` se cherche dans chaque ligne : il part de la page, pas du déroulé.
  const ligne = lignes(page).filter({ has: page.locator(`time[datetime="${visee.at}"]`) });

  // Le moteur refuse d'effacer une ligne de l'horloge : la page pose un retrait,
  // qui nomme la ligne et son heure.
  const envoi = page.waitForRequest(
    (request) => request.method() === "POST" && new URL(request.url()).pathname === "/autodj/conducteur/items.json",
    { timeout: 5_000 },
  );
  await ligne.getByRole("button", { name: /^Retirer / }).focus();
  await page.keyboard.press("Enter");
  expect((await envoi).postDataJSON()).toEqual({ suppress_at: visee.at, suppress_id: visee.id });

  const retrait = avis(page, /^« .+ » retiré du conducteur\./);
  await expect(retrait).toBeVisible();
  await expect(heure).toHaveCount(0);
  // Sa ligne partie, le bouton aussi : le focus revient au déroulé.
  await expect(deroule(page)).toBeFocused();
  expect(effaces, "aucune ligne effacée").toEqual([]);

  await retrait.getByRole("button", { name: "Annuler" }).click();
  await expect(avis(page, /^Retrait annulé : « .+ » est revenu à sa place\./)).toBeVisible();
  await expect(heure).toHaveCount(1);
  expect(effaces, "seul le retrait est effacé").toEqual([RETRAIT_POSE]);
  await expect(deroule(page)).toBeFocused();
});

test("un retrait sans réponse le dit en alerte, et la ligne reste", async ({ page }) => {
  // Une ligne de l'horloge pose un retrait, une ligne du pupitre s'efface : sans réponse, l'un comme l'autre.
  const sansReponse = (route: Route) =>
    ["POST", "DELETE"].includes(route.request().method()) ? route.abort("connectionrefused") : route.fallback();
  await page.route(RETRAIT, sansReponse);
  await page.route(LIGNE, sansReponse);
  await ouvrir(page, "programmateur");

  const ligne = lignes(page).filter({ has: retraits(page) }).first();
  const heure = await ligne.locator("time").getAttribute("datetime");
  await ligne.getByRole("button", { name: /^Retirer / }).click();

  await expect(alerte(page, "L’automate ne répond pas. Réessaie dans un instant.")).toBeVisible();
  await expect(deroule(page).locator(`time[datetime="${heure}"]`)).toHaveCount(1);
});

test("un conducteur qui ne répond plus le dit, et garde ses lignes", async ({ page }) => {
  await ouvrir(page, "animateur");
  const vieilli = "Le conducteur ne répond plus : ces lignes peuvent avoir changé.";
  await page.route(CONDUCTEUR, (route) => route.abort("connectionrefused"));

  await expect(avis(page, vieilli)).toBeVisible({ timeout: 10_000 });
  await expect(lignes(page).first()).toBeVisible();

  // Le conducteur revient de lui-même avec le moteur.
  await page.unroute(CONDUCTEUR);
  await expect(avis(page, vieilli)).toHaveCount(0, { timeout: 10_000 });
});
