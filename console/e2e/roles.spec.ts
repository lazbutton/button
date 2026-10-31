import { antenne, expect, seConnecter, test } from "./banc.ts";

// Ce que chaque rôle voit : la navigation, le menu du compte, les outils de
// l'admin et les pages réservées. Le pupitre, lui, est le même pour tous.

const ROLES = {
  animateur: {
    libelle: "Animateur",
    pages: ["Antenne", "Conducteur", "Réglages"],
    reglages: ["Mon compte"],
    programme: false,
    admin: false,
  },
  programmateur: {
    libelle: "Programmateur",
    pages: ["Antenne", "Conducteur", "Programmation", "Sons", "Réglages"],
    reglages: ["Mon compte"],
    programme: true,
    admin: false,
  },
  admin: {
    libelle: "Admin",
    pages: ["Antenne", "Conducteur", "Programmation", "Sons", "Réglages"],
    reglages: ["Comptes", "Station", "Mon compte", "Automate"],
    programme: true,
    admin: true,
  },
} as const;

for (const role of ["animateur", "programmateur", "admin"] as const) {
  const vu = ROLES[role];
  test(`${role} : la console suit le rôle`, async ({ page }) => {
    await seConnecter(page, role);
    await expect(antenne(page).getByRole("button", { name: /^Suivant/ })).toBeEnabled();
    const barre = page.getByRole("banner");
    const navigation = page.getByRole("navigation", { name: "Console" });
    await expect(navigation.getByRole("link")).toHaveText([...vu.pages]);

    // Le menu du compte dit le rôle, et garde le lien vers le code source.
    await barre.getByRole("button", { name: new RegExp(`^[A-Z]{2}, compte ${role} : menu$`) }).click();
    const menu = page.getByRole("menu");
    await expect(menu.getByText(vu.libelle, { exact: true })).toBeVisible();
    await expect(menu.getByRole("menuitem", { name: "Code source AGPL" })).toBeVisible();
    await page.keyboard.press("Escape");

    // Les outils de l'admin : la source du casque et le diagnostic de l'automate.
    await expect(barre.getByRole("button", { name: /^Source du casque/ })).toHaveCount(vu.admin ? 1 : 0);
    await barre.getByRole("button", { name: /^Antenne : / }).click();
    const detail = page.getByRole("dialog");
    await expect(detail.getByText("État de l’antenne")).toBeVisible();
    await expect(detail.getByRole("link", { name: "Diagnostic automate" })).toHaveCount(vu.admin ? 1 : 0);
    await page.keyboard.press("Escape");

    // Radix double le nom d'un onglet dans un texte caché : seul le texte visible compte.
    await navigation.getByRole("link", { name: "Réglages" }).click();
    await expect(page.getByRole("tablist").getByRole("tab")).toHaveText([...vu.reglages], { useInnerText: true });

    // Programmation et Sons : réservées aux programmateurs, même par l'adresse.
    for (const [chemin, onglet] of [
      ["/programmation", "Heures types"],
      ["/sons", "Bacs"],
    ] as const) {
      await page.goto(chemin);
      if (vu.programme) {
        await expect(page.getByRole("tab", { name: onglet })).toBeVisible();
      } else {
        await expect(page.getByText("Accès réservé", { exact: true })).toBeVisible();
        await expect(page.getByRole("tab", { name: onglet })).toHaveCount(0);
      }
    }
  });
}
