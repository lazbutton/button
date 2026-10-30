import { expect, seConnecter, test } from "./banc.ts";

test("se connecter, puis voir l’antenne", async ({ page }) => {
  await seConnecter(page, "animateur");

  // Le moteur de démo tient l'antenne avec l'horloge semée : un jingle ou un titre.
  const antenne = page.getByRole("region", { name: "À l’antenne" });
  await expect(antenne.getByText("À l’antenne", { exact: true })).toBeVisible();
  await expect(antenne).toContainText(/Jingle (grave|aigu)|Première écoute|Nuit claire|Signal faible/);
  await expect(antenne.getByRole("button", { name: "Passer en direct" })).toBeEnabled();

  // La bibliothèque vient du faux catalogue, par le relais de vite preview.
  await expect(page.getByRole("button", { name: "Diffuser Grande distance maintenant" })).toBeVisible();
});
