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
  const { password, accounts } = comptes();
  await page.goto("/");
  await page.getByLabel("Identifiant", { exact: true }).fill(accounts[role]);
  await page.getByLabel("Mot de passe", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Se connecter" }).click();
}

/** Un parcours échoue aussi sur une erreur JavaScript de la page, même sans effet visible. */
export const test = base.extend({
  page: async ({ page }, use) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await use(page);
    expect(errors, "erreurs JavaScript dans la page").toEqual([]);
  },
});

export { expect };
