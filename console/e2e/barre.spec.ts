import type { Page, Route } from "@playwright/test";
import { DEFAULT_SOURCE_URL, type Brand } from "../src/lib/brand.ts";
import { monitorSources, sourceById } from "../src/lib/monitorSource.ts";
import { antenne, expect, seConnecter, tenirLAntenne, test } from "./banc.ts";
import { engineRoutes } from "./routes.ts";

// La barre du haut, la même sur toutes les pages : ce qui passe, l'état de
// l'antenne, le casque et le compte.

// Ce que le relais envoie au moteur : le reste vient de la console.
const MOTEUR = new RegExp(`^/(${engineRoutes})`);
const versLeMoteur = (url: URL) => MOTEUR.test(url.pathname);

const barre = (page: Page) => page.getByRole("banner");
const casque = (page: Page) => barre(page).getByRole("button", { name: /^(Écouter au casque|Arrêter l’écoute)/ });
const echapper = (texte: string) => texte.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Le flux public, tel que la console le lit dans brand.json. */
async function adresseDuFlux(page: Page): Promise<URL> {
  const marque = (await (await page.request.get("/brand.json")).json()) as Brand;
  return new URL(sourceById(monitorSources(marque), "public").stream);
}

const versLeFlux = (flux: URL) => (url: URL) => url.origin === flux.origin && url.pathname === flux.pathname;

/** L'heure de chaque demande du flux, à partir de maintenant. */
function demandesDuFlux(page: Page, flux: URL): number[] {
  const heures: number[] = [];
  page.on("request", (demande) => {
    if (versLeFlux(flux)(new URL(demande.url()))) heures.push(Date.now());
  });
  return heures;
}

/** Les demandes du flux dans les 5 s qui suivent la première, comptées une fois ces 5 s passées. */
async function enCinqSecondes(page: Page, heures: number[]): Promise<number> {
  // Sans demande vue, l'adresse du flux a changé : compter ne prouverait rien.
  expect(heures.length, "demandes du flux vues par le parcours").toBeGreaterThan(0);
  const premiere = heures[0];
  await page.waitForTimeout(Math.max(0, premiere + 5_000 - Date.now()));
  return heures.filter((heure) => heure - premiere < 5_000).length;
}

/** Des trames MP3 muettes, 128 kbit/s à 44,1 kHz : 38 trames font une seconde. */
function trames(nombre: number): Buffer {
  const trame = Buffer.alloc(417);
  trame.set([0xff, 0xfb, 0x90, 0x44]);
  return Buffer.concat(Array.from({ length: nombre }, () => trame));
}

test("la barre dit ce qui passe, et l’état de l’antenne s’ouvre en détail", async ({ page }) => {
  await seConnecter(page, "animateur");
  await tenirLAntenne(page);

  // Le titre à l'antenne est le même que sur le pupitre.
  const titre = (await antenne(page).getByRole("paragraph").first().textContent()) ?? "";
  const enCours = barre(page).getByRole("link", { name: /^À l’antenne : / });
  await expect(enCours).toHaveAccessibleName(new RegExp(`^À l’antenne : ${echapper(titre)}[,.]`));

  const etat = barre(page).getByRole("button", { name: /^Antenne : / });
  await expect(etat).toHaveAccessibleName(/^Antenne : En onde, .+\. Santé : tout va bien\.$/);
  await etat.click();
  const detail = page.getByRole("dialog");
  await expect(detail.getByText("État de l’antenne")).toBeVisible();
  const sante = detail.getByRole("list", { name: "Santé antenne" }).getByRole("listitem");
  await expect(sante).toHaveCount(6);
  await expect(sante.filter({ hasText: "Moteur" })).toContainText("OK");
  // Le diagnostic de l'automate est réservé à l'admin.
  await expect(detail.getByRole("link", { name: "Diagnostic automate" })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(detail).toBeHidden();
  await expect(etat).toBeFocused();

  // D'une autre page, le titre ramène au pupitre.
  await page.getByRole("navigation", { name: "Console" }).getByRole("link", { name: "Conducteur" }).click();
  await expect(page).toHaveURL(/\/conducteur$/);
  await enCours.click();
  await expect(page).toHaveURL(/\/antenne$/);
  await expect(antenne(page)).toBeVisible();
});

test("moteur injoignable : le titre en cours dit qu’il n’a plus de nouvelles, puis repart", async ({ page }) => {
  // Le moteur de démo change de titre toutes les quatre secondes sur un jingle :
  // le relevé garde un titre fixe, que la barre doit garder après la panne.
  await page.route("**/live.json", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const reponse = await route.fetch();
    const releve = await reponse.json();
    await route.fulfill({ response: reponse, json: { ...releve, title: "Titre du banc", artist: "Studio" } });
  });
  await seConnecter(page, "animateur");
  // Loin du pupitre, la barre seule dit ce qui passe.
  await page.getByRole("navigation", { name: "Console" }).getByRole("link", { name: "Conducteur" }).click();
  await expect(page).toHaveURL(/\/conducteur$/);
  const enCours = barre(page).getByRole("link", { name: /^(À l’antenne|Sans nouvelles)/ });
  const decompte = /^À l’antenne : Titre du banc, Studio, reste \d+:\d{2}\. Ouvrir l’antenne\.$/;
  await expect(enCours).toHaveAccessibleName(decompte);
  await page.route(versLeMoteur, (route) => route.abort("connectionrefused"));

  await expect(barre(page).getByRole("button", { name: /^Antenne : / })).toHaveAccessibleName(
    "Antenne : Automate injoignable. Santé : état indisponible.",
    { timeout: 15_000 },
  );
  // Le dernier titre connu reste, sans son compte à rebours, et dit depuis quand il n'est plus lu.
  await expect(enCours).toHaveAccessibleName(
    /^Sans nouvelles depuis \d{2}:\d{2}\. Dernier titre connu : Titre du banc, Studio\. Ouvrir l’antenne\.$/,
  );
  await expect(enCours).toContainText(/Sans nouvelles depuis \d{2}:\d{2}$/);
  await expect(enCours).not.toContainText(/−\d+:\d{2}/);

  await page.unroute(versLeMoteur);
  await expect(enCours).toHaveAccessibleName(decompte, { timeout: 15_000 });
  await expect(enCours).not.toContainText("Sans nouvelles");
});

test("écouter l’antenne au casque, puis arrêter", async ({ page }) => {
  await seConnecter(page, "animateur");
  await expect(casque(page)).toHaveAccessibleName("Écouter au casque : Antenne publique");
  await expect(casque(page)).toHaveAttribute("aria-pressed", "false");

  await casque(page).click();
  await expect(casque(page)).toHaveAttribute("aria-pressed", "true");
  await expect(casque(page)).toHaveAccessibleName(/^Arrêter l’écoute\./);

  await casque(page).click();
  await expect(casque(page)).toHaveAttribute("aria-pressed", "false");
  await expect(casque(page)).toHaveAccessibleName("Écouter au casque : Antenne publique");
});

test("un flux muet au casque : la console le dit, sans marteler", async ({ page }) => {
  // Le banc coupe le flux : le casque n'entend rien, et le bouton le dit.
  const demandes = demandesDuFlux(page, await adresseDuFlux(page));
  await seConnecter(page, "animateur");
  await casque(page).click();
  await expect(casque(page)).toHaveAccessibleName("Arrêter l’écoute. Le flux ne répond pas : le casque réessaie seul", {
    timeout: 10_000,
  });
  // Chaque essai demande le flux jusqu'à trois fois : en PCM, en MSE, puis par
  // l'élément audio. Le backoff en laisse sept en 5 s au plus ; un essai toutes
  // les 200 ms en ferait plus de vingt.
  expect(await enCinqSecondes(page, demandes)).toBeLessThanOrEqual(24);
});

test("un flux qui s’arrête : le casque réessaie seul, sans marteler, et le dit", async ({ page }) => {
  // Comme Icecast quand on recrée le playout : il coupe les auditeurs du mount.
  // Ici, chaque connexion au flux rend une seconde de silence, puis se ferme.
  const flux = await adresseDuFlux(page);
  const connexions = demandesDuFlux(page, flux);
  await page.route(versLeFlux(flux), (route) =>
    route.fulfill({
      contentType: "audio/mpeg",
      headers: { "Access-Control-Allow-Origin": "*" },
      body: trames(38),
    }),
  );

  await seConnecter(page, "animateur");
  await casque(page).click();
  // Aucune reprise ne tient : le bouton le dit…
  await expect(casque(page)).toHaveAccessibleName("Arrêter l’écoute. Le flux ne répond pas : le casque réessaie seul", {
    timeout: 10_000,
  });
  // … et le casque se reconnecte seul, pendant l'écoute.
  const avant = connexions.length;
  await expect.poll(() => connexions.length, { timeout: 10_000 }).toBeGreaterThanOrEqual(avant + 2);
  // Sans marteler : chaque reprise ratée allonge l'attente, jusqu'à 3 s. En
  // 5 s, une poignée de connexions, pas vingt-cinq.
  expect(await enCinqSecondes(page, connexions)).toBeLessThanOrEqual(8);
});

test("un flux qui ne répond jamais : le casque cesse d’attendre, et le dit", async ({ page }) => {
  // Le serveur accepte la connexion sans jamais répondre : une machine
  // injoignable à mi-chemin, un proxy qui attend son amont. L'horloge de la
  // page saute les 8 s que le casque laisse à chaque demande.
  await page.clock.install();
  const flux = await adresseDuFlux(page);
  const enAttente: Route[] = [];
  await page.route(versLeFlux(flux), (route) => {
    enAttente.push(route);
  });

  await seConnecter(page, "animateur");
  await casque(page).click();
  // La demande attend sa réponse, et le bouton ne dit encore rien…
  await expect.poll(() => enAttente.length).toBe(1);
  await expect(casque(page)).not.toHaveAccessibleName(/ne répond pas/);
  // … puis, sans réponse en 8 s, le casque l'abandonne, et le dit.
  await page.clock.fastForward(8_000);
  await expect(casque(page)).toHaveAccessibleName("Arrêter l’écoute. Le flux ne répond pas : le casque réessaie seul");
  // Il demande ensuite le flux en MSE, puis par l'élément audio, qui
  // n'attendent pas plus : l'essai échoue, et le casque réessaie seul, après le
  // backoff.
  for (const demandes of [2, 3]) {
    await expect.poll(() => enAttente.length).toBe(demandes);
    await page.clock.fastForward(8_000);
  }
  const chemins = () => enAttente.map((route) => route.request().resourceType());
  await expect.poll(chemins).toEqual(["fetch", "fetch", "media", "fetch"]);
});

test("l’élément audio sans réponse : le casque le dit aussi", async ({ page }) => {
  // Le PCM et le MSE échouent tout de suite : le casque passe à l'élément
  // audio, dont la demande reste sans réponse. L'élément ne signale même pas
  // qu'il attend (waiting), ce que guette sa garde de calage : seule la borne
  // de play() peut finir l'essai.
  await page.clock.install();
  await page.addInitScript(() => document.addEventListener("waiting", (event) => event.stopPropagation(), true));
  const flux = await adresseDuFlux(page);
  const parLElement: Route[] = [];
  await page.route(versLeFlux(flux), (route) => {
    if (route.request().resourceType() === "media") parLElement.push(route);
    else void route.abort();
  });

  await seConnecter(page, "animateur");
  await casque(page).click();
  await expect.poll(() => parLElement.length).toBe(1);
  await expect(casque(page)).not.toHaveAccessibleName(/ne répond pas/);
  // L'élément n'attend pas plus qu'une demande du flux : l'essai échoue, et le
  // bouton le dit.
  await page.clock.fastForward(8_000);
  await expect(casque(page)).toHaveAccessibleName("Arrêter l’écoute. Le flux ne répond pas : le casque réessaie seul");
});

/**
 * Sert le flux par un seul chemin, l'élément audio ou le MSE : les autres
 * échouent tout de suite. Chaque essai demande le flux en PCM, puis en MSE :
 * des deux demandes fetch d'un essai, la première est celle du PCM. Rend
 * l'heure de chaque demande servie.
 */
async function servirPar(
  page: Page,
  flux: URL,
  chemin: "élément" | "MSE",
  corps: (demande: number) => Buffer,
): Promise<number[]> {
  // Compte les lectures que l'élément mène jusqu'au bout.
  await page.addInitScript(() => {
    const w = window as unknown as { finsDeLecture: number };
    w.finsDeLecture = 0;
    document.addEventListener("ended", () => {
      w.finsDeLecture += 1;
    }, true);
  });
  const heures: number[] = [];
  let fetchs = 0;
  await page.route(versLeFlux(flux), (route) => {
    const type = route.request().resourceType();
    const servie = chemin === "élément" ? type === "media" : type === "fetch" && ++fetchs % 2 === 0;
    if (!servie) return route.abort();
    heures.push(Date.now());
    return route.fulfill({
      contentType: "audio/mpeg",
      headers: { "Access-Control-Allow-Origin": "*" },
      body: corps(heures.length),
    });
  });
  return heures;
}

const finsDeLecture = (page: Page) =>
  page.evaluate(() => (window as unknown as { finsDeLecture: number }).finsDeLecture);

for (const chemin of ["élément", "MSE"] as const) {
  const par = chemin === "MSE" ? "en MSE" : "par l’élément audio";
  test(`${par}, un flux qui s’arrête : le casque le dit, sans marteler`, async ({ page }) => {
    // Chaque connexion rend un dixième de seconde, puis se ferme : l'élément
    // joue jusqu'au bout, mais aucune reprise ne tient 3 s.
    const servies = await servirPar(page, await adresseDuFlux(page), chemin, () => trames(4));
    await seConnecter(page, "animateur");
    await casque(page).click();
    await expect(casque(page)).toHaveAccessibleName("Arrêter l’écoute. Le flux ne répond pas : le casque réessaie seul");
    // Chaque reprise ratée allonge l'attente, jusqu'à 3 s. En 5 s, une poignée
    // de connexions, pas une quinzaine.
    expect(await enCinqSecondes(page, servies)).toBeLessThanOrEqual(8);
    expect(await finsDeLecture(page), "connexions jouées jusqu'au bout").toBeGreaterThan(0);
  });
}

test("par l’élément audio, la reprise ne compte qu’après 3 s de son", async ({ page }) => {
  // La première connexion rend un dixième de seconde, puis le flux revient,
  // pour 8 s.
  const servies = await servirPar(page, await adresseDuFlux(page), "élément", (demande) =>
    trames(demande === 1 ? 4 : 38 * 8),
  );
  await seConnecter(page, "animateur");
  await casque(page).click();
  await expect(casque(page)).toHaveAccessibleName("Arrêter l’écoute. Le flux ne répond pas : le casque réessaie seul");
  // Le flux revenu joue, mais l'alerte reste tant qu'il n'a pas tenu 3 s…
  await expect.poll(() => servies.length).toBe(2);
  await page.waitForTimeout(Math.max(0, servies[1] + 1_000 - Date.now()));
  await expect(casque(page)).toHaveAccessibleName("Arrêter l’écoute. Le flux ne répond pas : le casque réessaie seul");
  // … puis elle s'efface, et le bouton redonne le retard du casque.
  await expect(casque(page)).toHaveAccessibleName(/^Arrêter l’écoute\. Retard du casque : \d+ ms$/, { timeout: 10_000 });
});

test("l’admin choisit la source de son casque, et la retrouve", async ({ page }) => {
  await seConnecter(page, "admin");
  const source = barre(page).getByRole("button", { name: /^Source du casque/ });
  await expect(source).toHaveAccessibleName("Source du casque : Antenne publique. Changer.");

  await source.click();
  await page.getByRole("menuitemradio", { name: /^Conducteur \(fichiers\)/ }).click();
  await expect(source).toHaveAccessibleName("Source du casque : Conducteur (fichiers). Changer.");
  await expect(casque(page)).toHaveAccessibleName("Écouter au casque : Conducteur (fichiers)");

  await page.reload();
  await expect(source).toHaveAccessibleName("Source du casque : Conducteur (fichiers). Changer.");
});

test("le menu du compte : qui est connecté, « Mon compte », puis la déconnexion", async ({ page }) => {
  await seConnecter(page, "programmateur");
  await barre(page).getByRole("button", { name: "Compte programmateur : menu" }).click();
  const menu = page.getByRole("menu", { name: "Compte programmateur : menu" });
  await expect(menu.getByText("programmateur", { exact: true })).toBeVisible();
  await expect(menu.getByText("Programmateur", { exact: true })).toBeVisible();

  await menu.getByRole("menuitem", { name: "Mon compte" }).click();
  await expect(page).toHaveURL(/\/reglages\?onglet=compte$/);
  await expect(page.getByRole("tabpanel", { name: "Mon compte" })).toBeVisible();

  await barre(page).getByRole("button", { name: "Compte programmateur : menu" }).click();
  await page.getByRole("menuitem", { name: "Se déconnecter" }).click();
  await expect(page.getByRole("button", { name: "Se connecter" })).toBeVisible();
  // La session est close chez le moteur aussi : recharger ne la rend pas.
  await page.reload();
  await expect(page.getByRole("button", { name: "Se connecter" })).toBeVisible();
});

test("le lien « Code source » ouvre les sources dans un nouvel onglet", async ({ page, context }) => {
  await seConnecter(page, "animateur");
  await barre(page).getByRole("button", { name: "Compte animateur : menu" }).click();
  const lien = page.getByRole("menuitem", { name: "Code source AGPL" });
  // L'adresse vient de la marque, sinon du dépôt de BUTTON.
  const marque = (await (await page.request.get("/brand.json")).json()) as { suite?: { sourceUrl?: string } };
  const adresse = marque.suite?.sourceUrl || DEFAULT_SOURCE_URL;
  await expect(lien).toHaveAttribute("href", adresse);

  const onglet = context.waitForEvent("page", { timeout: 5_000 });
  await lien.click();
  const sources = await onglet;
  await expect(sources).toHaveURL(adresse);
  // La console reste ouverte à côté.
  await expect(antenne(page)).toBeVisible();
  await sources.close();
});
