import { alerte, antenne, avis, expect, seConnecter, test } from "./banc.ts";

// La page des bacs, avec le compte qui les prépare : le programmateur. Un bac
// créé ici reste dans le moteur de démo jusqu'à la fin du lancement.

test("« Diffuser maintenant » sur un bac sans son prêt dit que rien n'est parti", async ({ page }) => {
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.goto("/sons");

  await page.getByRole("complementary", { name: "Bacs" }).getByRole("button", { name: "Nouveau" }).click();
  const creation = page.getByRole("dialog", { name: "Nouveau bac" });
  await creation.getByLabel("Nom").fill("Bac sans son");
  await creation.getByRole("radio", { name: /^Fichiers/ }).click();
  await creation.getByRole("button", { name: "Créer le bac" }).click();
  await expect(creation).toBeHidden();

  await page.getByRole("region", { name: "Bac sans son" }).getByRole("button", { name: "Diffuser maintenant" }).click();
  await expect(alerte(page, "Ce bac n'a aucun son prêt : rien n'est parti à l'antenne.")).toBeVisible();
  await expect(avis(page, /envoyé à l'antenne/)).toHaveCount(0);
});
