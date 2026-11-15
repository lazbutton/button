import type { Route } from "@playwright/test";
import { antenne, expect, seConnecter, test } from "./banc.ts";

// Reconnaître un fichier dès l'envoi (FON-82). Le moteur du banc n'a ni bibliothèque
// Beets, ni le rangement allumé : le parcours allume le rangement dans /account.json,
// et répond ici à /fiches/envois.json comme le moteur, d'abord « en route », puis
// avec un doublon et un titre reconnu. Un doublon se range comme les autres : la
// console le signale, sans rien retirer.

type Fichier = { dest: string; name: string };

function rapport(fichier: Fichier, arrive: boolean) {
  const vide = { dest: fichier.dest, name: fichier.name, in_bank: false, id: null, path: null, duplicates: [], recognized: null, searched: false };
  if (!arrive) return vide;
  const ici = { ...vide, in_bank: true, id: 9, path: `10-rotation/${fichier.name}`, searched: true };
  if (fichier.name.startsWith("Nina Simone")) {
    const autre = { id: 1, artist: "Nina Simone", title: "Feeling Good", path: "10-rotation/feeling good.flac", zone: "rotation", collection: "rotation" };
    return { ...ici, duplicates: [autre] };
  }
  return { ...ici, recognized: { artist: "Les Marées Hautes", title: "Estuaire", level: "sûr", source: "Deezer" } };
}

test("un doublon et un titre reconnu se disent dans la file, avant de quitter la page", async ({ page }) => {
  await seConnecter(page, "programmateur");
  await expect(antenne(page)).toBeVisible();
  await page.route("**/account.json", async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback();
    const reponse = await route.fetch();
    const compte = (await reponse.json()) as Record<string, unknown>;
    await route.fulfill({ response: reponse, json: { ...compte, features: { bank_tidy: true } } });
  });
  let demandes = 0;
  await page.route("**/fiches/envois.json", async (route: Route) => {
    const { files } = route.request().postDataJSON() as { files: Fichier[] };
    demandes += 1;
    await route.fulfill({ json: { fiches: true, files: files.map((one) => rapport(one, demandes > 1)) } });
  });

  await page.goto("/sons?onglet=importer&vue=ajouter");
  await expect(page.getByRole("heading", { name: "Ajouter à la banque" })).toBeVisible();
  await page
    .locator('input[type="file"]:not([webkitdirectory])')
    .first()
    .setInputFiles([
      { name: "Nina Simone - Feeling Good.mp3", mimeType: "audio/mpeg", buffer: Buffer.from("ID3 un") },
      { name: "Les Marées Hautes - Estuaire.mp3", mimeType: "audio/mpeg", buffer: Buffer.from("ID3 deux") },
    ]);
  await page.getByRole("button", { name: "Envoyer 2 fichiers" }).click();

  const file = page.getByRole("list", { name: "Fichiers à envoyer" });
  await expect(file.getByText("Doublon de Nina Simone - Feeling Good (Rotation)")).toBeVisible({ timeout: 15_000 });
  await expect(file.getByText("Reconnu : Les Marées Hautes, Estuaire")).toBeVisible();
  // Le doublon est envoyé comme les autres : rien n'est retiré de la file.
  await expect(file.getByText("Envoyé")).toHaveCount(2);
  // Tout est dit : la console ne redemande plus.
  const vues = demandes;
  await page.waitForTimeout(6_000);
  expect(demandes).toBe(vues);
});
