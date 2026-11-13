import { alerte, avis, expect, seConnecter, test } from "./banc.ts";

// Les messages en bas à droite de l'écran (src/ui/AppToast.tsx). Leur ton vient
// du geste, jamais de leurs mots. Une fenêtre ouverte ne les cache ni à l'œil,
// ni aux lecteurs d'écran, et un clic sur eux ne la ferme pas.

test("au-dessus d’une fenêtre ouverte, un message se lit, dit son ton, et se ferme sans elle", async ({ page }) => {
  await seConnecter(page, "admin");
  await page.getByRole("navigation", { name: "Console" }).getByRole("link", { name: "Réglages" }).click();

  // Le compte semé n'est pas touché : le parcours joue la réponse du moteur,
  // une acceptation, puis un refus.
  let refus: string | null = null;
  await page.route("**/users/*.json", (route) => {
    if (route.request().method() !== "PUT") return route.fallback();
    return refus ? route.fulfill({ status: 409, json: { error: refus } }) : route.fulfill({ status: 200, json: {} });
  });

  await page.getByRole("button", { name: "Actions pour animateur", exact: true }).click();
  await page.getByRole("menuitem", { name: "Fiche du compte" }).click();
  const fiche = page.getByRole("dialog", { name: "animateur" });
  await fiche.getByRole("button", { name: "Enregistrer les notes" }).click();

  // La fenêtre cache le reste de la page aux lecteurs d'écran, pas le message.
  const fait = avis(page, "Notes de « animateur » enregistrées.");
  await expect(fait).toBeVisible();
  await expect(fait.getByRole("img", { name: "Succès" })).toBeVisible();
  // Il est au-dessus de la fenêtre : il se ferme d'un clic, et elle reste ouverte.
  await fait.getByRole("button", { name: "Fermer le message" }).click();
  await expect(fait).toHaveCount(0);
  await expect(fiche).toBeVisible();

  // Un refus du moteur s'annonce en alerte, quels que soient ses mots : rien
  // dans « trop longues » ne dit un échec.
  refus = "Ces notes sont trop longues.";
  await fiche.getByRole("button", { name: "Enregistrer les notes" }).click();
  const echec = alerte(page, refus);
  await expect(echec).toBeVisible();
  await expect(echec.getByRole("img", { name: "Erreur" })).toBeVisible();
  await expect(fiche).toBeVisible();

  // La fenêtre fermée, le message reste, le temps d'être lu.
  await page.keyboard.press("Escape");
  await expect(fiche).toHaveCount(0);
  await expect(echec).toBeVisible();
});
