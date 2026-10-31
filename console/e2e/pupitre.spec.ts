import type { Page } from "@playwright/test";
import { antenne, avis, bibliotheque, expect, file, secondes, seConnecter, tenirLAntenne, tenirLaFile, test } from "./banc.ts";

// Le pupitre au quotidien, avec le compte qui s'en sert le plus : l'animateur.
// Les gestes qui changent l'antenne passent par le moteur de démo, partagé par
// tous les parcours d'un lancement.

test.beforeEach(async ({ page }) => {
  await seConnecter(page, "animateur");
  await expect(antenne(page)).toBeVisible();
});

const recherche = (page: Page) => bibliotheque(page).getByRole("searchbox", { name: "Chercher dans la bibliothèque" });
const lignes = (page: Page) => file(page).getByRole("listitem");
const poignees = (page: Page) => file(page).getByRole("button", { name: /^Déplacer / });
const poignee = (titre: string) => `Déplacer ${titre} : flèches haut et bas`;

/** L'avancée du titre à l'antenne, en secondes : « 0:12 / 3:00 » donne 12. */
async function ecoule(page: Page): Promise<number> {
  const avancee = await antenne(page).getByText(/^\d+:\d{2} \/ \d+:\d{2}$/).textContent();
  return secondes(avancee?.split(" / ")[0] ?? null);
}

/** Le titre de chaque ligne mobile de la file, lu dans le nom de sa poignée. */
async function titresDesLignes(page: Page): Promise<string[]> {
  const noms = await poignees(page).evaluateAll((boutons) => boutons.map((bouton) => bouton.getAttribute("aria-label") ?? ""));
  return noms.map((nom) => nom.replace(/^Déplacer /, "").replace(/ : flèches haut et bas$/, ""));
}

/**
 * Deux lignes voisines de la file aux titres différents : l'horloge de démo
 * repasse les mêmes titres, et un échange entre deux titres pareils ne se
 * verrait pas.
 */
async function voisines(page: Page): Promise<{ rang: number; haut: string; bas: string }> {
  const titres = await titresDesLignes(page);
  const rang = titres.findIndex((titre, index) => index > 0 && titre !== titres[index - 1]);
  if (rang < 0) throw new Error(`Aucune paire de titres voisins différents dans la file : ${titres.join(", ")}.`);
  return { rang, haut: titres[rang - 1], bas: titres[rang] };
}

test("Espace passe au titre suivant, une seule fois, et s’écrit dans un champ", async ({ page }) => {
  await tenirLAntenne(page);
  const sauts: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "DELETE" && new URL(request.url()).pathname === "/live.json") sauts.push(request.url());
  });

  // Dans la recherche, Espace s'écrit et ne touche pas à l'antenne. Échap vide
  // la recherche et rend la main à la page.
  await recherche(page).click();
  await page.keyboard.type("Grande distance");
  await expect(recherche(page)).toHaveValue("Grande distance");
  await page.keyboard.press("Escape");
  await expect(recherche(page)).toHaveValue("");
  await expect(recherche(page)).not.toBeFocused();

  // Hors des contrôles, Espace passe le titre : l'avancée repart de zéro. Deux
  // appuis rapprochés ne passent qu'un titre.
  await expect.poll(() => ecoule(page)).toBeGreaterThanOrEqual(3);
  await page.keyboard.press("Space");
  await page.keyboard.press("Space");
  await expect.poll(() => ecoule(page)).toBeLessThan(3);
  expect(sauts, "titres passés").toHaveLength(1);
});

test("« / » mène à la recherche, et Entrée met le titre trouvé à la suite", async ({ page }) => {
  await expect(recherche(page)).not.toBeFocused();
  await page.keyboard.press("/");
  await expect(recherche(page)).toBeFocused();
  await page.keyboard.type("Annonce");
  await expect(bibliotheque(page).getByRole("listitem")).toHaveCount(1);

  // Le parcours lit la demande au moteur, pas la file : sans titre à l'antenne
  // dans sa base, le moteur de démo date la ligne de l'heure de l'appui. Après
  // un « Suivant », il a de l'avance sur son horloge, et la file range alors la
  // ligne avant le titre à l'antenne, parmi ce qui est passé.
  const insertion = page.waitForRequest(
    (request) => request.method() === "POST" && new URL(request.url()).pathname === "/autodj/conducteur/items.json",
    { timeout: 5_000 },
  );
  await page.keyboard.press("Enter");
  const demande = (await insertion).postDataJSON();
  expect(demande).toMatchObject({ title: "Annonce locale", kind: "pub" });
  expect(demande, "à la suite, pas avant une ligne").not.toHaveProperty("before_id");
  await expect(avis(page, "Mis à la suite.")).toBeVisible();
});

test("la pré-écoute passe au casque seul, puis lui rend l’antenne", async ({ page }) => {
  const casque = page.getByRole("banner").getByRole("button", { name: /^(Écouter au casque|Arrêter l’écoute)/ });
  await casque.click();
  await expect(casque).toHaveAttribute("aria-pressed", "true");
  const gestes: string[] = [];
  page.on("request", (request) => {
    if (request.method() !== "GET") gestes.push(`${request.method()} ${request.url()}`);
  });

  const fichier = page.waitForResponse((response) => new URL(response.url()).pathname.startsWith("/library/media/"), {
    timeout: 5_000,
  });
  await bibliotheque(page).getByRole("button", { name: "Pré-écouter Bande large au casque" }).click();
  expect((await fichier).ok(), "fichier de la pré-écoute").toBe(true);
  const arreter = bibliotheque(page).getByRole("button", { name: "Arrêter la pré-écoute de Bande large" });
  await expect(arreter).toHaveAttribute("aria-pressed", "true");
  // Le casque d'antenne se tait pendant la pré-écoute…
  await expect(casque).toHaveAttribute("aria-pressed", "false");

  await arreter.click();
  await expect(bibliotheque(page).getByRole("button", { name: "Pré-écouter Bande large au casque" })).toHaveAttribute(
    "aria-pressed",
    "false",
  );
  // … puis reprend.
  await expect(casque).toHaveAttribute("aria-pressed", "true");
  expect(gestes, "la pré-écoute ne touche pas à l’antenne").toEqual([]);
});

test("Diffuser met le titre à l’antenne tout de suite", async ({ page }) => {
  await bibliotheque(page).getByRole("button", { name: "Diffuser Jingle station maintenant" }).click();
  await expect(avis(page, /^Envoyé|^À l’antenne/)).toBeVisible();
  await expect(antenne(page).getByText("Jingle station", { exact: true })).toBeVisible();
  await expect(page.getByRole("banner").getByRole("link", { name: /^À l’antenne : Jingle station[,.]/ })).toBeVisible();
});

test("une ligne de la file se déplace au clavier", async ({ page }) => {
  await tenirLaFile(page, async () => {
    const { rang, haut, bas } = await voisines(page);

    await poignees(page).nth(rang).focus();
    await page.keyboard.press("ArrowUp");

    await expect(poignees(page).nth(rang - 1)).toHaveAccessibleName(poignee(bas));
    await expect(poignees(page).nth(rang)).toHaveAccessibleName(poignee(haut));
    // Le focus suit la ligne : elle peut monter encore.
    await expect(poignees(page).nth(rang - 1)).toBeFocused();
  });
});

test("une ligne de la file se déplace à la souris", async ({ page }) => {
  await tenirLaFile(page, async () => {
    const { rang, haut, bas } = await voisines(page);

    await poignees(page).nth(rang).dragTo(poignees(page).nth(rang - 1));

    await expect(poignees(page).nth(rang - 1)).toHaveAccessibleName(poignee(bas));
    await expect(poignees(page).nth(rang)).toHaveAccessibleName(poignee(haut));
  });
});

// Une ligne qui prend la première place de la file ne part jamais avant
// maintenant. Montée devant une ligne commencée depuis plus longtemps qu'elle ne
// dure, une ligne de 4 s reste donc en tête de la file, au lieu d'être rangée
// parmi ce qui est passé.
test("une ligne montée devant une ligne déjà commencée prend la tête de la file", async ({ page }) => {
  // Le moteur de démo date de l'appui une ligne mise à la suite. Derrière le
  // titre lancé par « Diffuser », elle prend la tête de la file, déjà commencée.
  await bibliotheque(page).getByRole("button", { name: "Diffuser Grande distance maintenant" }).click();
  await expect(avis(page, /^Envoyé|^À l’antenne/)).toBeVisible();
  await bibliotheque(page).getByRole("button", { name: /^Mettre à la suite : Annonce locale,/ }).click();
  await expect(avis(page, "Mis à la suite.")).toBeVisible();
  // La tête de la file doit avoir commencé depuis plus que la durée de la
  // ligne montée : le temps du moteur passe pour de vrai.
  await page.waitForTimeout(5_000);

  await tenirLaFile(page, async () => {
    const tete = lignes(page).filter({ has: page.getByRole("button", { name: /^Déplacer / }) }).first();
    const depart = Date.parse((await tete.getByRole("time").getAttribute("datetime")) ?? "");
    expect(Date.now() - depart, "la tête de la file a commencé depuis plus de 4 s").toBeGreaterThan(4_000);
    // La ligne à monter, mise à la suite pendant que la file est tenue : la
    // sienne ne finit pas avant le geste.
    await bibliotheque(page).getByRole("button", { name: /^Mettre à la suite : Jingle station,/ }).click();
    await expect(avis(page, "Mis à la suite.")).toBeVisible();
    const rang = (await titresDesLignes(page)).indexOf("Jingle station");
    expect(rang, "« Jingle station » sous la tête de la file").toBeGreaterThan(0);

    // Elle monte d'un cran à chaque appui, jusqu'en tête. Chaque appui attend
    // que la file montre le précédent.
    for (let place = rang; place > 0; place -= 1) {
      await poignees(page).nth(place).focus();
      await page.keyboard.press("ArrowUp");
      await expect(poignees(page).nth(place - 1)).toHaveAccessibleName(poignee("Jingle station"));
    }

    // Ménage : rangées derrière elle, les lignes du pupitre posées ici
    // resteraient des minutes dans la file des parcours suivants.
    for (const titre of ["Jingle station", "Annonce locale", "Grande distance"]) {
      const retirer = file(page).getByRole("button", { name: `Retirer ${titre} de la file` });
      for (let reste = await retirer.count(); reste > 0; reste -= 1) {
        await retirer.first().click();
        await expect(retirer).toHaveCount(reste - 1);
      }
    }
  });
});

test("une ligne retirée de la file revient avec « Annuler »", async ({ page }) => {
  await tenirLAntenne(page);
  // La dernière ligne visible vient de l'horloge. Son heure de passage la désigne
  // sans doute possible : les titres, eux, reviennent.
  const derniere = lignes(page).last();
  const heure = (await derniere.getByRole("time").textContent()) ?? "";
  expect(heure).toMatch(/^\d{2}:\d{2}:\d{2}$/);
  const retirer = (await derniere.getByRole("button", { name: /^Retirer / }).getAttribute("aria-label")) ?? "";
  const ligne = lignes(page).filter({ hasText: heure });
  await expect(ligne).toHaveCount(1);

  await ligne.getByRole("button", { name: retirer }).click();
  const retrait = avis(page, "Retiré de la file.");
  await expect(retrait).toBeVisible();
  await expect(ligne).toHaveCount(0);

  await retrait.getByRole("button", { name: "Annuler" }).click();
  await expect(avis(page, "Annulé.")).toBeVisible();
  await expect(ligne).toHaveCount(1);
  await expect(ligne.getByRole("button", { name: retirer })).toBeVisible();
});

test("fermer le panneau du direct rend le focus à « Passer en direct »", async ({ page }) => {
  const direct = antenne(page).getByRole("button", { name: "Passer en direct" });
  const panneau = page.getByRole("dialog");

  // Au clavier : Entrée ouvre, Échap ferme.
  await direct.focus();
  await page.keyboard.press("Enter");
  await expect(panneau).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(panneau).toBeHidden();
  await expect(direct).toBeFocused();

  // À la souris : le bouton « Fermer » du panneau.
  await direct.click();
  await expect(panneau).toBeVisible();
  await panneau.getByRole("button", { name: "Fermer" }).click();
  await expect(panneau).toBeHidden();
  await expect(direct).toBeFocused();

  // Au doigt, Safari ne donne pas le focus au bouton touché : il était ailleurs
  // à l'ouverture, et le panneau le rend quand même à « Passer en direct ».
  await recherche(page).focus();
  await direct.dispatchEvent("click");
  await expect(panneau).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(panneau).toBeHidden();
  await expect(direct).toBeFocused();
});
