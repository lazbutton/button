import { readFileSync } from "node:fs";
import { expect, test as base, type Page } from "@playwright/test";
import type { Role } from "../src/api/roles.ts";

// Ce que engine/tests/e2e/seed.py a semé pour ce lancement : un compte par
// rôle, avec un mot de passe tiré pour ce lancement seulement.
type Comptes = { password: string; accounts: Record<Role, string> };

export function comptes(): Comptes {
  const path = process.env.E2E_COMPTES;
  if (!path) throw new Error("E2E_COMPTES manque : lancer les parcours avec ./scripts/e2e.sh.");
  return JSON.parse(readFileSync(path, "utf8")) as Comptes;
}

/** Ouvre la console et passe l'écran de connexion avec le compte du rôle. */
export async function seConnecter(page: Page, role: Role): Promise<void> {
  await page.goto("/");
  await remplirLaConnexion(page, role);
}

/** Remplit l'écran de connexion déjà affiché, par exemple après une session expirée. */
export async function remplirLaConnexion(page: Page, role: Role): Promise<void> {
  const { password, accounts } = comptes();
  await page.getByLabel("Identifiant", { exact: true }).fill(accounts[role]);
  await page.getByLabel("Mot de passe", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Se connecter" }).click();
}

/** Un parcours échoue aussi sur une erreur JavaScript de la page, même sans effet visible. */
export const test = base.extend({
  // Le banc ne sort pas de la machine. brand.json nomme le flux et le now.json
  // d'une vraie station, que le casque de la console demande dès l'ouverture :
  // ces requêtes échouent. Un lien vers un autre site, comme « Code source »,
  // ouvre une page vide à son adresse.
  context: async ({ context, baseURL }, use) => {
    const banc = new URL(baseURL ?? "http://127.0.0.1").host;
    await context.route(
      (url) => url.host !== banc,
      (route) =>
        route.request().isNavigationRequest()
          ? route.fulfill({ contentType: "text/html", body: "<title>Hors du banc</title>" })
          : route.abort("blockedbyclient"),
    );
    await use(context);
  },
  page: async ({ page }, use) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await use(page);
    expect(errors, "erreurs JavaScript dans la page").toEqual([]);
  },
});

export { expect };

// Le pupitre (page Antenne), par ses trois régions.
export const antenne = (page: Page) => page.getByRole("region", { name: "À l’antenne" });
export const file = (page: Page) => page.getByRole("region", { name: "File" });
export const bibliotheque = (page: Page) => page.getByRole("region", { name: "Bibliothèque" });

/** Un message de la console annoncé comme un état : une confirmation, une information. */
export const avis = (page: Page, texte: string | RegExp) => page.getByRole("status").filter({ hasText: texte });

/** Un message de la console annoncé comme une alerte : un échec, une panne. */
export const alerte = (page: Page, texte: string | RegExp) => page.getByRole("alert").filter({ hasText: texte });

/** « 2:57 », « restant 2:57 » ou « 1:02:57 », en secondes. */
export function secondes(texte: string | null): number {
  const match = /(\d+(?::\d{2}){1,2})\s*$/.exec(texte ?? "");
  if (!match) throw new Error(`Pas de durée dans « ${texte} ».`);
  return match[1].split(":").reduce((total, partie) => total * 60 + Number(partie), 0);
}

/**
 * Le moteur de démo enchaîne seul les titres de l'horloge, et un jingle ne dure
 * que 4 s : la file bouge à chaque fin de titre. Avant de toucher à la file ou
 * au temps qui passe, un parcours passe jusqu'à un titre qui tient l'antenne
 * une minute au moins.
 */
export async function tenirLAntenne(page: Page): Promise<void> {
  const reste = antenne(page).getByRole("timer");
  const suivant = antenne(page).getByRole("button", { name: /^Suivant/ });
  await expect(suivant, "« Suivant » est actif : ni direct, ni antenne coupée").toBeEnabled();
  await expect(async () => {
    const restant = secondes(await reste.getAttribute("aria-label"));
    if (restant < 60) await suivant.click();
    expect(restant, "secondes restantes du titre à l’antenne").toBeGreaterThanOrEqual(60);
  }).toPass({ intervals: [1_600], timeout: 20_000 });
}
