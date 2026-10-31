import { expect, seConnecter, test } from "./banc.ts";

// Choisir l'animateur d'une émission. Un programmateur voit les comptes qui
// peuvent passer en direct, sans lire la liste des comptes, réservée aux admins.

test("programmateur : le compte du plateau propose les animateurs", async ({ page }) => {
  await seConnecter(page, "programmateur");
  await page.getByRole("navigation", { name: "Console" }).getByRole("link", { name: "Programmation" }).click();
  await page.getByRole("tab", { name: "Semaine" }).click();
  await page.getByRole("button", { name: "Émission", exact: true }).first().click();
  const fenetre = page.getByRole("dialog");
  await fenetre.getByRole("combobox", { name: "Compte du plateau" }).click();
  // Le banc ne sème qu'un compte qui peut passer en direct : l'admin.
  await expect(page.getByRole("option", { name: "admin", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("listbox")).toHaveCount(0);
  await expect(fenetre.getByText("Mets à jour le moteur")).toHaveCount(0);
  await expect(fenetre.getByText("La liste des comptes ne répond pas")).toHaveCount(0);
  await fenetre.getByRole("button", { name: "Annuler" }).click();
  await expect(fenetre).toHaveCount(0);
});
