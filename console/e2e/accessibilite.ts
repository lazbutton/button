import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

// L'accessibilité vue par axe-core : un défaut grave ou critique fait échouer
// le parcours. banc.ts vérifie la page où finit chaque parcours, et
// accessibilite.spec.ts passe chaque écran, en clair, en sombre et sur un
// téléphone.

/**
 * Les défauts graves ou critiques que la console garde en connaissance de cause,
 * par règle d'axe : les éléments en cause, ou ce qui les contient, chacun avec sa
 * raison en commentaire. Tout autre défaut grave ou critique fait échouer le
 * parcours. Ceux relevés quand axe-core est entré dans les parcours (TST-03) sont
 * corrigés : la liste est vide.
 */
const DEFAUTS_CONNUS: Record<string, string[]> = {};

/**
 * Les couleurs de texte de tokens.css trop pâles pour les fonds de la console,
 * telles qu'axe les mesure, excusées en connaissance de cause. Un jeton corrigé
 * change de couleur : cette liste ne l'excuse plus, et sa nouvelle couleur est
 * vérifiée.
 */
const TEXTES_PALES: string[] = [];

type Noeud = Awaited<ReturnType<AxeBuilder["analyze"]>>["violations"][number]["nodes"][number];

function textePale(noeud: Noeud): boolean {
  const mesure = noeud.any.find((check) => check.id === "color-contrast")?.data as { fgColor?: string } | undefined;
  return TEXTES_PALES.includes(mesure?.fgColor ?? "");
}

/**
 * Les défauts graves ou critiques de la page, hors défauts connus : un par
 * élément, à lire dans un rapport. Le moteur de démo fait bouger la page
 * pendant l'analyse : un défaut n'est rapporté que s'il est encore là à la
 * seconde.
 */
export async function defautsGraves(page: Page): Promise<string[]> {
  const premiere = await analyser(page);
  return premiere.length === 0 ? premiere : analyser(page);
}

async function analyser(page: Page): Promise<string[]> {
  // Sans animation, et après celles qui finissent : un menu ou un avis encore en
  // train d'apparaître fausserait les contrastes.
  const reduit = await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter((animation) => animation.playState === "running")
        .filter((animation) => animation.effect?.getComputedTiming().endTime !== Infinity)
        .map((animation) => animation.finished.catch(() => undefined)),
    ),
  );
  let violations: Awaited<ReturnType<AxeBuilder["analyze"]>>["violations"];
  try {
    ({ violations } = await new AxeBuilder({ page }).analyze());
  } finally {
    await page.emulateMedia({ reducedMotion: reduit ? "reduce" : "no-preference" });
  }

  const graves = violations.flatMap((violation) =>
    violation.nodes
      .filter((noeud) => noeud.impact === "serious" || noeud.impact === "critical")
      .map((noeud) => ({ regle: violation.id, noeud })),
  );
  // L'élément d'un défaut connu se cherche dans la page, par le sélecteur qu'axe
  // donne. Remplacé depuis l'analyse, il se reconnaît à la balise qu'axe a relevée.
  const connus = await page.evaluate(
    (elements) =>
      elements.map(([cible, html, selecteurs]) => {
        if (selecteurs.length === 0) return false;
        const selecteur = selecteurs.join(", ");
        try {
          const element = document.querySelector(cible);
          if (element) return Boolean(element.closest(selecteur));
          const releve = document.createElement("template");
          releve.innerHTML = html;
          return Boolean(releve.content.firstElementChild?.matches(selecteur));
        } catch {
          return false; // un élément dans un cadre ou un shadow DOM : la console n'en a pas
        }
      }),
    graves.map(({ regle, noeud }) => [String(noeud.target[0]), noeud.html, DEFAUTS_CONNUS[regle] ?? []] as const),
  );
  return graves
    .filter(({ regle, noeud }, rang) => !connus[rang] && !(regle === "color-contrast" && textePale(noeud)))
    .map(({ regle, noeud }) => {
      const pourquoi = (noeud.failureSummary ?? "").replace(/Fix (any|all) of the following:/g, "").replace(/\s+/g, " ");
      return `${regle} (${noeud.impact}) ${noeud.target.join(" ")} : ${pourquoi.trim()}`;
    });
}

/** Fait échouer le parcours sur un défaut d'accessibilité grave ou critique de la page, hors défauts connus. */
export async function verifierAccessibilite(page: Page, ecran = "la page"): Promise<void> {
  expect(await defautsGraves(page), `défauts d’accessibilité graves ou critiques : ${ecran}`).toEqual([]);
}
