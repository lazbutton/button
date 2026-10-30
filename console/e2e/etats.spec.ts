import type { Page, Route } from "@playwright/test";
import { READ_DEADLINE_MS } from "../src/api/readDeadline.ts";
import { antenne, avis, bibliotheque, comptes, expect, file, remplirLaConnexion, seConnecter, test } from "./banc.ts";
import { engineRoutes } from "./routes.ts";

// Ce que la console dit quand le moteur répond mal. Chaque cas est simulé par
// page.route devant le vrai moteur de démo : session expirée (401), droit
// manquant (403), moteur injoignable (connexion refusée), moteur muet (une
// lecture qui ne reçoit jamais de réponse), moteur arrêté derrière nginx (502
// en HTML), envoi trop lourd pour nginx (413 en HTML) et route absente,
// c'est-à-dire un moteur plus ancien que la console (404).

// Ce que le relais envoie au moteur : le reste vient de la console.
const MOTEUR = new RegExp(`^/(${engineRoutes})`);
const versLeMoteur = (url: URL) => MOTEUR.test(url.pathname);

/**
 * La même demande, vers une route que le moteur ne connaît pas : il répond 404,
 * comme un moteur plus ancien. Le préfixe /antenne/ fait passer la demande par
 * le relais, jusqu'au moteur. Rend le statut que le moteur a répondu.
 */
async function versUneRouteAbsente(route: Route): Promise<number> {
  const adresse = new URL(route.request().url());
  adresse.pathname = "/antenne/route-absente.json";
  const reponse = await route.fetch({ url: adresse.toString() });
  await route.fulfill({ response: reponse });
  return reponse.status();
}

/**
 * En prod, nginx relaie l'API : moteur arrêté, il répond lui-même 502, avec sa
 * page HTML. Le banc n'a pas de nginx devant le moteur : le parcours la sert.
 */
const PAGE_502 = [
  "<html>",
  "<head><title>502 Bad Gateway</title></head>",
  "<body>",
  "<center><h1>502 Bad Gateway</h1></center>",
  "<hr><center>nginx</center>",
  "</body>",
  "</html>",
  "",
].join("\r\n");
const moteurArrete = (route: Route) => route.fulfill({ status: 502, contentType: "text/html", body: PAGE_502 });

const suivant = (page: Page) => antenne(page).getByRole("button", { name: /^Suivant/ });
const passer = (route: Route) => route.request().method() === "DELETE";

test("session expirée pendant un geste : la console le dit", async ({ page }) => {
  await seConnecter(page, "animateur");
  await page.route("**/live.json", (route) =>
    passer(route) ? route.fulfill({ status: 401, json: { error: "unauthenticated" } }) : route.continue(),
  );

  await suivant(page).click();
  await expect(avis(page, "Session expirée. Reconnecte-toi.")).toBeVisible();
});

test("session expirée : la console redemande le mot de passe, puis rend le pupitre", async ({ page }) => {
  await seConnecter(page, "animateur");
  await expect(suivant(page)).toBeEnabled();
  // Le moteur ne reconnaît plus la session, jusqu'à la connexion suivante réussie.
  let expiree = true;
  await page.route(versLeMoteur, async (route) => {
    if (new URL(route.request().url()).pathname === "/login.json") {
      const reponse = await route.fetch();
      if (reponse.ok()) expiree = false;
      return route.fulfill({ response: reponse });
    }
    return expiree ? route.fulfill({ status: 401, json: { error: "unauthenticated" } }) : route.continue();
  });

  // La lecture suivante du pupitre tombe sur la session expirée.
  await expect(page.getByRole("button", { name: "Se connecter" })).toBeVisible();
  await expect(suivant(page)).toHaveCount(0);

  await remplirLaConnexion(page, "animateur");
  await expect(suivant(page)).toBeEnabled();
  await expect(page.getByRole("button", { name: "Se connecter" })).toHaveCount(0);
});

test("droit manquant : le geste refusé dit quel droit il faut", async ({ page }) => {
  await seConnecter(page, "animateur");
  await page.route("**/live.json", (route) =>
    passer(route) ? route.fulfill({ status: 403, json: { error: "forbidden" } }) : route.continue(),
  );

  await suivant(page).click();
  await expect(avis(page, "Il faut le droit antenne. Demande à un admin si tu dois pouvoir le faire.")).toBeVisible();
  await expect(antenne(page)).toBeVisible();
});

test("moteur injoignable à l’ouverture : la console le dit, puis repart", async ({ page }) => {
  await seConnecter(page, "animateur");
  await expect(suivant(page)).toBeEnabled();
  await page.route(versLeMoteur, (route) => route.abort("connectionrefused"));

  await page.reload();
  await expect(page.getByText("Radiotomate est indisponible")).toBeVisible();
  await expect(page.getByText(/^L’automate ne répond pas\./)).toBeVisible();

  await page.unroute(versLeMoteur);
  await page.getByRole("button", { name: "Réessayer" }).click();
  await expect(suivant(page)).toBeEnabled();
});

test("moteur injoignable pendant un geste : la console le dit", async ({ page }) => {
  await seConnecter(page, "animateur");
  await page.route("**/live.json", (route) => (passer(route) ? route.abort("connectionrefused") : route.continue()));

  await suivant(page).click();
  await expect(avis(page, "L’automate ne répond pas. Réessaie dans un instant.")).toBeVisible();
});

test("moteur arrêté derrière nginx pendant un geste : la console le dit, sans la page de nginx", async ({ page }) => {
  await seConnecter(page, "animateur");
  await page.route("**/live.json", (route) => (passer(route) ? moteurArrete(route) : route.continue()));

  await suivant(page).click();
  await expect(avis(page, "L’automate ne répond pas. Réessaie dans un instant.")).toBeVisible();
  await expect(avis(page, /Bad Gateway/)).toHaveCount(0);
});

test("moteur arrêté derrière nginx à la connexion : la console ne parle pas de mot de passe", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Se connecter" })).toBeVisible();
  // Le moteur s'arrête avant l'envoi : /login.json, puis le repli sur le
  // formulaire de /login, reçoivent la page de nginx.
  await page.route(versLeMoteur, moteurArrete);

  await remplirLaConnexion(page, "animateur");
  await expect(avis(page, "L’automate ne répond pas. Vérifie qu’il tourne, puis réessaie.")).toBeVisible();
});

test("connexion par le formulaire de repli : un mot de passe refusé se dit comme tel", async ({ page }) => {
  await page.goto("/");
  // /login.json ne répond pas : la console passe par le formulaire de /login,
  // où le moteur refuse le mot de passe par une page HTML, en 401.
  await page.route("**/login.json", (route) => route.abort("connectionrefused"));

  await page.getByLabel("Identifiant", { exact: true }).fill(comptes().accounts.animateur);
  await page.getByLabel("Mot de passe", { exact: true }).fill("pas-le-bon");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(avis(page, /^Identifiant ou mot de passe incorrect\./)).toBeVisible();
});

test("envoi trop lourd pour nginx : le bac le dit, sans la page de nginx", async ({ page }) => {
  await seConnecter(page, "programmateur");
  await expect(suivant(page)).toBeEnabled();
  await page.goto("/sons");
  // nginx refuse un envoi de plus de 512 Mo (client_max_body_size) par sa page HTML.
  const page413 = PAGE_502.replaceAll("502 Bad Gateway", "413 Request Entity Too Large");
  await page.route("**/carts/*/sounds.json*", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 413, contentType: "text/html", body: page413 })
      : route.continue(),
  );

  await page
    .locator('input[type="file"][accept^="audio"]')
    .setInputFiles({ name: "emission.wav", mimeType: "audio/wav", buffer: Buffer.from("RIFF") });
  await expect(
    avis(page, "Envoi trop lourd pour le serveur. Dépose moins de fichiers à la fois, ou des fichiers plus légers."),
  ).toBeVisible();
  await expect(avis(page, /Request Entity|Le moteur ne répond pas/)).toHaveCount(0);
});

test("moteur injoignable, pupitre ouvert : la barre le dit, puis repart", async ({ page }) => {
  await seConnecter(page, "animateur");
  await expect(suivant(page)).toBeEnabled();
  const etat = page.getByRole("banner").getByRole("button", { name: /^Antenne : / });
  await page.route(versLeMoteur, (route) => route.abort("connectionrefused"));

  // Le dernier relevé, encore à l'écran, ne fait pas croire que tout va bien.
  await expect(etat).toHaveAccessibleName("Antenne : Automate injoignable. Santé : état indisponible.", {
    timeout: 15_000,
  });

  await page.unroute(versLeMoteur);
  await expect(etat).toHaveAccessibleName(/^Antenne : En onde/, { timeout: 15_000 });
});

test("moteur muet, pupitre ouvert : la barre le dit, puis repart", async ({ page }) => {
  // Deux attentes du délai de lecture, en plus de la connexion.
  test.slow();
  await seConnecter(page, "animateur");
  await expect(suivant(page)).toBeEnabled();
  const etat = page.getByRole("banner").getByRole("button", { name: /^Antenne : / });
  // Le moteur accepte la connexion, puis ne répond plus : boucle Quart bloquée,
  // ou téléphone dont le réseau perd les paquets. Ses lectures restent pendantes.
  await page.route(versLeMoteur, () => {});

  await expect(etat).toHaveAccessibleName("Antenne : Automate injoignable. Santé : état indisponible.", {
    timeout: READ_DEADLINE_MS + 10_000,
  });

  // Les lectures restées sans réponse ne retiennent pas les suivantes.
  await page.unroute(versLeMoteur);
  await expect(etat).toHaveAccessibleName(/^Antenne : En onde/, { timeout: READ_DEADLINE_MS + 10_000 });
});

test("moteur injoignable pour la file seule : la file ne se dit pas vide", async ({ page }) => {
  const conducteur = "**/autodj/conducteur.json*";
  await page.route(conducteur, (route) => route.abort("connectionrefused"));
  await seConnecter(page, "animateur");
  await expect(suivant(page)).toBeEnabled();

  await expect(file(page)).toContainText("La file ne répond pas.");
  await expect(file(page)).not.toContainText("Rien à la suite.");

  // La file revient d'elle-même avec le moteur.
  await page.unroute(conducteur);
  await expect(file(page).getByRole("listitem").first()).toBeVisible({ timeout: 10_000 });
});

test("route absente : sans les émissions ni l’état de l’antenne, le pupitre reste", async ({ page }) => {
  const absentes = new Map<string, number>();
  await page.route(/\/antenne\/(emissions|state)\.json/, async (route) => {
    absentes.set(new URL(route.request().url()).pathname, await versUneRouteAbsente(route));
  });
  await seConnecter(page, "animateur");
  // Le moteur a bien répondu 404 aux deux routes avant ce qui suit.
  await expect
    .poll(() => Object.fromEntries(absentes))
    .toEqual({ "/antenne/emissions.json": 404, "/antenne/state.json": 404 });

  await expect(suivant(page)).toBeEnabled();
  await expect(file(page).getByRole("listitem").first()).toBeVisible();
  await expect(bibliotheque(page).getByRole("listitem").first()).toBeVisible();
  // L'état de l'antenne ne se lit plus : la barre ne dit pas que tout va bien.
  await expect(page.getByRole("banner").getByRole("button", { name: /^Antenne : / })).toHaveAccessibleName(
    /Santé : état indisponible\.$/,
  );
});

test("route absente pendant un geste : la console le dit en français", async ({ page }) => {
  // Le moteur répond le 404 de Quart, en anglais : la console dit pourquoi, et quoi faire.
  await seConnecter(page, "animateur");
  await page.route("**/live.json", (route) => (passer(route) ? versUneRouteAbsente(route) : route.continue()));

  await suivant(page).click();
  await expect(avis(page, "Cette action demande un moteur plus récent. Mets à jour le moteur.")).toBeVisible();
  await expect(avis(page, /requested URL/)).toHaveCount(0);
});
