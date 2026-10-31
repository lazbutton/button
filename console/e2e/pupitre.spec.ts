import type { Locator, Page } from "@playwright/test";
import { CONDUCTEUR_JSON } from "../src/api/rundownLive.ts";
import type { Rundown } from "../src/api/types.ts";
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
 *
 * La première ligne reste en place, tant que le moteur range les lignes
 * déplacées à partir du plus tôt de leurs départs, même passé : voir le
 * parcours en attente plus bas. Derrière la première ligne, chaque ligne
 * déplacée finit après elle.
 */
async function voisines(page: Page): Promise<{ rang: number; haut: string; bas: string }> {
  const titres = await titresDesLignes(page);
  const rang = titres.findIndex((titre, index) => index > 1 && titre !== titres[index - 1]);
  if (rang < 0) throw new Error(`Aucune paire de titres voisins différents après la première ligne : ${titres.join(", ")}.`);
  return { rang, haut: titres[rang - 1], bas: titres[rang] };
}

/**
 * La dernière ligne de la file que « Annuler » remet à sa place : une ligne de
 * l'horloge, qu'un retrait masque. Une ligne du pupitre retirée est effacée, et
 * « Annuler » la remet à la suite, à une autre heure. La file ne dit pas d'où
 * vient une ligne : le parcours le lit au moteur. Une ligne verrouillée n'a pas
 * de bouton « Retirer » : le moteur de démo verrouille aussi la ligne de son
 * titre en cours, parfois loin dans la file.
 *
 * L'heure de passage exacte de la ligne, l'attribut `datetime` de son heure, la
 * désigne : aucune autre ligne du moteur ne l'a. Le masque d'un retrait vaut
 * pour une heure exacte, et ne cache donc qu'elle. L'heure affichée, à la
 * seconde, peut être celle de deux lignes.
 */
async function derniereLigneDeLHorloge(page: Page): Promise<Locator> {
  const reponse = await page.request.get(CONDUCTEUR_JSON);
  expect(reponse.ok(), "file lue au moteur").toBe(true);
  const { items } = (await reponse.json()) as Rundown;
  // L'heure exacte de chaque ligne qui a un bouton « Retirer », dans l'ordre de la file.
  const heures = await lignes(page)
    .filter({ has: page.getByRole("button", { name: /^Retirer / }) })
    .getByRole("time")
    .evaluateAll((balises) => balises.map((balise) => balise.getAttribute("datetime") ?? ""));
  const heure = heures
    .filter((at) => {
      const memes = items.filter((item) => item.at === at);
      return memes.length === 1 && memes[0].origin === "clock";
    })
    .at(-1);
  if (!heure) throw new Error(`Aucune ligne de l'horloge à retirer parmi : ${heures.join(", ")}.`);
  return lignes(page).filter({ has: page.locator(`time[datetime="${heure}"]`) });
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

// Défaut connu du moteur : reorder_desk_items (engine/radiotomate/scheduler/desk.py)
// range les lignes déplacées à partir du plus tôt de leurs départs, même passé.
// Une ligne de 4 s montée devant une ligne commencée depuis plus de 4 s finit
// donc avant maintenant : la file la range parmi ce qui est passé, au lieu de
// la montrer en tête, et le moteur l'efface au bout de 30 s. Le dernier appui
// échoue ici.
test.fixme("une ligne montée en tête de la file y reste, même devant une ligne déjà commencée", async ({ page }) => {
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
    const rang = (await titresDesLignes(page)).lastIndexOf("Jingle station");
    expect(rang, "« Jingle station » sous la tête de la file").toBeGreaterThan(0);

    // Elle monte d'un cran à chaque appui, jusqu'en tête. Chaque appui attend
    // que la file montre le précédent.
    for (let place = rang; place > 0; place -= 1) {
      await poignees(page).nth(place).focus();
      await page.keyboard.press("ArrowUp");
      await expect(poignees(page).nth(place - 1)).toHaveAccessibleName(poignee("Jingle station"));
    }
  });
});

test("une ligne retirée de la file revient avec « Annuler »", async ({ page }) => {
  // La file tenue, aucune ligne du haut n'en sort pendant le geste : elle ne
  // glisse pas. Le message du retrait reste aussi : ses 8 s ne passent pas.
  await tenirLaFile(page, async () => {
    const ligne = await derniereLigneDeLHorloge(page);
    await expect(ligne).toHaveCount(1);
    const retirer = ligne.getByRole("button", { name: /^Retirer / });
    const nom = (await retirer.getAttribute("aria-label")) ?? "";

    await retirer.click();
    const retrait = avis(page, "Retiré de la file.");
    await expect(retrait).toBeVisible();
    await expect(ligne).toHaveCount(0);

    await retrait.getByRole("button", { name: "Annuler" }).click();
    await expect(avis(page, "Annulé.")).toBeVisible();
    await expect(ligne).toHaveCount(1);
    await expect(ligne.getByRole("button", { name: nom, exact: true })).toBeVisible();
  });
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
