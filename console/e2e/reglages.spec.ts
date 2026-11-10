import { expect, seConnecter, test } from "./banc.ts";

// Réglages, pour un admin : un menu à gauche, la station d'abord, puis son compte.
// Il se parcourt au clavier, et la partie ouverte est dans l'adresse.

test("le menu des réglages se parcourt au clavier, et la partie ouverte est dans l’adresse", async ({ page }) => {
  await seConnecter(page, "admin");
  await page.getByRole("navigation", { name: "Console" }).getByRole("link", { name: "Réglages" }).click();
  const menu = page.getByRole("tablist", { name: "Parties des réglages" });
  const partie = (nom: string) => menu.getByRole("tab", { name: nom });
  await expect(menu).toHaveAttribute("aria-orientation", "vertical");
  await expect(partie("Comptes")).toHaveAttribute("aria-selected", "true");

  // En colonne, les flèches du haut et du bas passent d'une partie à l'autre.
  await partie("Comptes").focus();
  await page.keyboard.press("ArrowDown");
  await expect(partie("Station")).toBeFocused();
  await expect(partie("Station")).toHaveAttribute("aria-selected", "true");
  await expect(page).toHaveURL(/\/reglages\?onglet=station$/);
  await expect(page.getByRole("heading", { name: "Station", level: 2 })).toBeVisible();

  await page.keyboard.press("End");
  await expect(partie("Mon compte")).toHaveAttribute("aria-selected", "true");
  await expect(page).toHaveURL(/\/reglages\?onglet=compte$/);

  // La première partie n'a pas besoin d'être dans l'adresse.
  await page.keyboard.press("Home");
  await expect(partie("Comptes")).toHaveAttribute("aria-selected", "true");
  await expect(page).toHaveURL(/\/reglages$/);

  // Une partie s'ouvre aussi par son adresse, et le rechargement la garde.
  await page.goto("/reglages?onglet=automate");
  await expect(partie("Automate")).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "Automate", level: 2 })).toBeVisible();
});

test("sur un écran étroit, le menu passe en ligne au-dessus de la partie", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await seConnecter(page, "admin");
  // La connexion finie, la barre du haut nomme le compte : ouvrir une page avant l'interromprait.
  await expect(page.getByRole("banner").getByRole("button", { name: /, compte .+ : menu$/ })).toBeVisible();
  await page.goto("/reglages");
  const menu = page.getByRole("tablist", { name: "Parties des réglages" });
  await expect(menu).toHaveAttribute("aria-orientation", "horizontal");

  // En ligne, ce sont les flèches de gauche et de droite.
  await menu.getByRole("tab", { name: "Comptes" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(menu.getByRole("tab", { name: "Station" })).toHaveAttribute("aria-selected", "true");

  // Rien ne déborde de côté.
  const largeur = await page.evaluate(() => ({
    page: document.documentElement.scrollWidth,
    ecran: document.documentElement.clientWidth,
  }));
  expect(largeur.page, "défilement de côté").toBeLessThanOrEqual(largeur.ecran);
});
