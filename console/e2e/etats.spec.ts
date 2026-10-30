import type { Page, Route } from "@playwright/test";
import {
  alerte,
  antenne,
  avis,
  bibliotheque,
  expect,
  file,
  remplirLaConnexion,
  seConnecter,
  tenirLAntenne,
  test,
} from "./banc.ts";
import { engineRoutes } from "./routes.ts";

// Ce que la console dit quand le moteur répond mal. Chaque cas est simulé par
// page.route devant le vrai moteur de démo : session expirée (401), droit
// manquant (403), moteur injoignable (connexion refusée) et route absente,
// c'est-à-dire un moteur plus ancien que la console (404). La page Automate
// passe aussi par le catalogue : un refus ou un catalogue injoignable y sont
// simulés devant le faux catalogue.

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

const suivant = (page: Page) => antenne(page).getByRole("button", { name: /^Suivant/ });
const passer = (route: Route) => route.request().method() === "DELETE";

test("session expirée pendant un geste : la console le dit", async ({ page }) => {
  await seConnecter(page, "animateur");
  await page.route("**/live.json", (route) =>
    passer(route) ? route.fulfill({ status: 401, json: { error: "unauthenticated" } }) : route.continue(),
  );

  await suivant(page).click();
  await expect(alerte(page, "Session expirée. Reconnecte-toi.")).toBeVisible();
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
  await expect(alerte(page, "Il faut le droit antenne. Demande à un admin si tu dois pouvoir le faire.")).toBeVisible();
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
  await expect(alerte(page, "L’automate ne répond pas. Réessaie dans un instant.")).toBeVisible();
});

test("moteur injoignable pendant « Annuler » : la console le dit", async ({ page }) => {
  await seConnecter(page, "animateur");
  await tenirLAntenne(page);
  // La dernière ligne visible vient de l'horloge : son heure de passage la désigne.
  const heure = (await file(page).getByRole("listitem").last().getByRole("time").textContent()) ?? "";
  expect(heure).toMatch(/^\d{2}:\d{2}:\d{2}$/);
  const ligne = file(page).getByRole("listitem").filter({ hasText: heure });
  await expect(ligne).toHaveCount(1);
  await ligne.getByRole("button", { name: /^Retirer / }).click();
  const retrait = avis(page, "Retiré de la file.");
  await expect(retrait).toBeVisible();
  await expect(ligne).toHaveCount(0);

  // Le retrait est passé. L'annulation, elle, ne trouve plus le moteur.
  await page.route(/\/autodj\/conducteur\/items/, (route) => route.abort("connectionrefused"));
  await retrait.getByRole("button", { name: "Annuler" }).click();
  await expect(alerte(page, "L’automate ne répond pas. Réessaie dans un instant.")).toBeVisible();
});

test("moteur injoignable, pupitre ouvert : la barre et le pupitre le disent, puis repartent", async ({ page }) => {
  await seConnecter(page, "animateur");
  await tenirLAntenne(page);
  await expect(file(page).getByRole("listitem").first()).toBeVisible();
  const etat = page.getByRole("banner").getByRole("button", { name: /^Antenne : / });
  const reste = antenne(page).getByRole("timer");
  const avancee = antenne(page).getByText(/^\d+:\d{2} \/ \d+:\d{2}$/);
  const fin = antenne(page).getByText(/^fin \d{2}:\d{2}$/);
  const vieillie = "La file ne répond plus : ces lignes peuvent avoir changé.";
  await expect(avancee).toBeVisible();
  await expect(fin).toBeVisible();
  await page.route(versLeMoteur, (route) => route.abort("connectionrefused"));

  // Le dernier relevé, encore à l'écran, ne fait pas croire que tout va bien.
  await expect(etat).toHaveAccessibleName("Antenne : Automate injoignable. Santé : état indisponible.", {
    timeout: 15_000,
  });
  // Le pupitre dit depuis quand, et garde le dernier titre connu : aucun des textes de repli
  // n'est là. Son temps ne se compte plus, et sa file se dit vieillie.
  await expect(alerte(page, /^Automate injoignable Le pupitre ne reçoit plus de nouvelles depuis \d{2}:\d{2} :/)).toBeVisible();
  await expect(antenne(page)).toContainText("Sans nouvelles");
  await expect(antenne(page)).not.toContainText(/Rien à l’antenne|L’antenne ne répond pas|Aucun titre connu/);
  await expect(reste).toHaveAccessibleName("inconnu —");
  await expect(avancee).toHaveCount(0);
  await expect(fin).toHaveCount(0);
  await expect(avis(page, vieillie)).toBeVisible({ timeout: 10_000 });
  await expect(file(page).getByRole("listitem").first()).toBeVisible();
  // Suivant reste actif, et dit en alerte pourquoi rien ne passe.
  await suivant(page).click();
  await expect(alerte(page, "L’automate ne répond pas. Réessaie dans un instant.")).toBeVisible();

  await page.unroute(versLeMoteur);
  await expect(etat).toHaveAccessibleName(/^Antenne : En onde/, { timeout: 15_000 });
  await expect(alerte(page, "Automate injoignable")).toHaveCount(0);
  await expect(antenne(page)).not.toContainText("Sans nouvelles");
  await expect(reste).toHaveAccessibleName(/^restant \d/);
  await expect(avis(page, vieillie)).toHaveCount(0, { timeout: 10_000 });
});

test("moteur injoignable pendant un direct : la carte reste celle du direct", async ({ page }) => {
  // Le moteur de démo n'a pas de harbor : son relevé dit qu'un encodeur tient l'antenne.
  await page.route("**/live.json", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    const reponse = await route.fetch();
    const releve = await reponse.json();
    await route.fulfill({ response: reponse, json: { ...releve, source: "harbor", title: "Direct du banc", artist: "Studio" } });
  });
  await seConnecter(page, "animateur");
  const encodeur = antenne(page).getByRole("button", { name: "Infos encodeur" });
  await expect(encodeur).toBeVisible();
  await expect(antenne(page)).toContainText("Direct du banc");
  await page.route(versLeMoteur, (route) => route.abort("connectionrefused"));

  await expect(antenne(page)).toContainText("Sans nouvelles", { timeout: 15_000 });
  await expect(antenne(page).getByRole("timer")).toHaveAccessibleName("inconnu —");
  // Le dernier titre connu reste, et les gestes restent ceux du direct.
  await expect(antenne(page)).toContainText("Direct du banc");
  await expect(encodeur).toBeVisible();
  await expect(antenne(page).getByRole("button", { name: /^(Suivant|Passer en direct)/ })).toHaveCount(0);
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

test("moteur injoignable pour la file seule, déjà lue : ses lignes restent, vieillies", async ({ page }) => {
  await seConnecter(page, "animateur");
  await expect(file(page).getByRole("listitem").first()).toBeVisible();
  const conducteur = "**/autodj/conducteur.json*";
  const vieillie = "La file ne répond plus : ces lignes peuvent avoir changé.";
  await page.route(conducteur, (route) => route.abort("connectionrefused"));

  await expect(avis(page, vieillie)).toBeVisible({ timeout: 10_000 });
  await expect(file(page).getByRole("listitem").first()).toBeVisible();
  // Le reste du pupitre se lit encore : il ne se dit pas sans nouvelles.
  await expect(alerte(page, "Automate injoignable")).toHaveCount(0);
  await expect(antenne(page)).not.toContainText("Sans nouvelles");

  await page.unroute(conducteur);
  await expect(avis(page, vieillie)).toHaveCount(0, { timeout: 10_000 });
  await expect(file(page).getByRole("listitem").first()).toBeVisible();
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
  await expect(alerte(page, "Cette action demande un moteur plus récent. Mets à jour le moteur.")).toBeVisible();
  await expect(page.getByText(/requested URL/)).toHaveCount(0);
});

test("page Automate : un geste refusé ou sans réponse s’annonce en alerte", async ({ page }) => {
  await seConnecter(page, "admin");
  await page.getByRole("navigation", { name: "Console" }).getByRole("link", { name: "Réglages" }).click();
  await page.getByRole("tab", { name: "Automate" }).click();
  // Les gestes de dépannage se confirment dans une fenêtre.
  const geste = async (bouton: string, confirmation: string) => {
    await page.getByRole("button", { name: bouton, exact: true }).click();
    await page.getByRole("dialog").getByRole("button", { name: confirmation, exact: true }).click();
  };

  // Vider les files passe par le moteur.
  for (const [reponse, message] of [
    [{ status: 403, json: { error: "forbidden" } }, "Réservé à un admin. Reconnecte-toi avec ce compte."],
    [null, "L’automate ne répond pas. Réessaie dans un instant."],
    [{ status: 401, json: { error: "unauthenticated" } }, "Session expirée. Reconnecte-toi."],
  ] as const) {
    await page.route("**/antenne/flush.json", (route) =>
      reponse ? route.fulfill(reponse) : route.abort("connectionrefused"),
    );
    await geste("Vider les files", "Vider les files");
    await expect(alerte(page, message)).toBeVisible();
    await page.unroute("**/antenne/flush.json");
  }

  // Retirer les titres hors bacs passe par le catalogue.
  for (const [reponse, message] of [
    [{ status: 403, json: { error: "forbidden" } }, "Réservé à un admin. Reconnecte-toi avec ce compte."],
    [null, "Le catalogue ne répond pas. Réessaie dans un instant."],
  ] as const) {
    await page.route("**/library/prune", (route) => (reponse ? route.fulfill(reponse) : route.abort("connectionrefused")));
    await geste("Retirer les titres hors bacs", "Retirer");
    await expect(alerte(page, message)).toBeVisible();
    await page.unroute("**/library/prune");
  }
});
