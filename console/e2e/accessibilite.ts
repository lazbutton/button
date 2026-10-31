import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

// L'accessibilité vue par axe-core : un défaut grave ou critique fait échouer
// le parcours. banc.ts vérifie la page où finit chaque parcours, et
// accessibilite.spec.ts passe chaque écran, en clair, en sombre et sur un
// téléphone.

/**
 * Les défauts que la console avait déjà quand axe-core est entré dans les
 * parcours (TST-03), par règle d'axe : les éléments en cause, ou ce qui les
 * contient. Ils restent à corriger dans console/src, et un défaut corrigé sort
 * de cette liste. Tout autre défaut grave ou critique fait échouer le parcours.
 */
const DEFAUTS_CONNUS: Record<string, string[]> = {
  // Des textes trop pâles pour leur fond, estompés par une opacité ou d'une
  // couleur de Radix Themes. Les couleurs de tokens.css sont dans TEXTES_PALES.
  "color-contrast": [
    "kbd", // les touches, à 55 %
    ".tb-menu-tag", // l'étiquette AGPL du menu du compte, à 60 %
    ".engine-rundown-row.is-past", // les lignes passées du conducteur, à 62 %
    ".conducteur-strip-remain", // le temps qui reste au conducteur, rouge éclairci de blanc
    ".rt-BaseMenuLabel", // le titre d'une section de menu
    '.rt-Badge[data-accent-color="amber"]',
    // Un bouton plein du gris de l'accent : blanc sur gris.
    '.rt-variant-solid:is([data-accent-color=""], [data-accent-color="gray"])',
  ],
  // Un aria-label qui ne reprend pas le texte affiché (WCAG 2.5.3) : la commande
  // vocale ne trouve pas l'élément par ce qu'elle lit.
  "label-content-name-mismatch": [
    ".tb-account",
    ".tb-air",
    ".tb-now",
    ".tb-listen-source",
    ".banque-dest-trigger",
    ".health-pill",
    ".ant-hit",
    ".prog-run",
    ".prog-day",
  ],
  // Les grilles de la Semaine et de l'Agenda n'ont pas de lignes (role="row").
  "aria-required-children": [".prog-week-grid", ".ag-week-grid"],
  "aria-required-parent": [".prog-week-grid", ".ag-week-grid"],
  // Une zone qui défile, sans rien pour y entrer au clavier.
  "scrollable-region-focusable": [".ag-week-frame", ".engine-rundown-list"],
  // Le détail de l'état de l'antenne s'ouvre en dialogue sans nom.
  "aria-dialog-name": [".tb-pop"],
  // Un menu ouvert cache le reste de la page (data-aria-hidden, posé par Radix)
  // sans en retirer les éléments qui prennent le focus.
  "aria-hidden-focus": ["[data-aria-hidden]"],
};

/**
 * Les couleurs de texte de tokens.css trop pâles pour les fonds de la console,
 * telles qu'axe les mesure. Un jeton corrigé change de couleur : cette liste ne
 * l'excuse plus, et sa nouvelle couleur est vérifiée.
 */
const TEXTES_PALES = [
  "#737373", // --app-text-faint, en clair comme en sombre
  "#ff4d4d", // --app-live et --app-danger, sur fond clair
  "#bf5d36", // --app-warn-ink en clair : le temps qui reste d'un titre qui finit
];

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
