import { titlesLabel } from "./bankContent.ts";
import { fileName, type BankTitle, type FicheField } from "./bankTitles.ts";

/**
 * Corriger la fiche d'un titre ou d'un lot (FON-66) : ce que la console envoie à
 * `POST /media/titles/edit.json`, et ce qu'elle dit de la réponse. Les règles
 * sont dans le moteur (engine/radiotomate/services/title_edits.py). Sans React.
 */

/** Un lot prend 500 titres au plus : le moteur refuse au-delà. */
export const MAX_LOT = 500;

/** Les champs qu'une personne corrige, dans l'ordre de la fiche. */
export const EDIT_FIELDS: FicheField[] = ["title", "artist", "album", "year", "genre", "famille"];

export const EDIT_LABELS: Record<FicheField, string> = {
  title: "Titre",
  artist: "Artiste",
  album: "Album",
  year: "Année",
  genre: "Genre",
  famille: "Famille",
};

/**
 * Les quatorze familles, comme les nomme le moteur (`FAMILIES`,
 * engine/radiotomate/fiches/rules.py) : `titleEdits.test.ts` les compare.
 */
export const FAMILIES: Array<{ name: string; label: string }> = [
  { name: "hip-hop", label: "Hip-hop" },
  { name: "reggae-dub", label: "Reggae, dub" },
  { name: "jazz", label: "Jazz" },
  { name: "soul-funk", label: "Soul, funk" },
  { name: "monde", label: "Musiques du monde" },
  { name: "electro", label: "Électro" },
  { name: "chanson", label: "Chanson" },
  { name: "rock", label: "Rock" },
  { name: "blues", label: "Blues" },
  { name: "folk-country", label: "Folk, country" },
  { name: "pop", label: "Pop" },
  { name: "film", label: "Musique de film" },
  { name: "classique", label: "Classique" },
  { name: "experimental", label: "Expérimental" },
];

/** La fiche d'un titre, telle que le formulaire la tient : du texte, champ par champ. */
export type FicheForm = Record<FicheField, string>;

export type EditLot = {
  titles: Array<{
    id: number;
    values: Partial<FicheForm>;
    /** Ce que la console a montré : un titre changé depuis refuse le lot. */
    expected: Partial<FicheForm>;
  }>;
};

export type TitleIssue = { id: number; label: string; code: string; reason: string };
export type SelectionChange = { id: number; name: string; gained: number; lost: number };

export type EditOutcome = {
  dry_run: boolean;
  /** Le lot au journal ; null pour un essai, ou quand rien n'a changé. */
  entry: number | null;
  /** Les titres écrits, ou qui le seraient. */
  written: number;
  waiting: TitleIssue[];
  kept: TitleIssue[];
  refused: TitleIssue[];
  unchanged: number;
  selections: SelectionChange[];
};

export type Tone = "success" | "error" | "info";

/** La fiche d'un titre, en texte : une année vide plutôt que 0. */
export function formOf(title: BankTitle): FicheForm {
  return {
    title: title.title,
    artist: title.artist,
    album: title.album,
    year: title.year ? String(title.year) : "",
    genre: title.genre,
    famille: title.famille,
  };
}

/** Ce qui ne va pas dans une année tapée, ou "" : quatre chiffres, ou rien. */
export function yearProblem(text: string): string {
  const value = text.trim();
  if (!value) return "";
  if (!/^\d{4}$/.test(value) || Number(value) < 1000) return "L'année s'écrit en quatre chiffres, comme 2019.";
  return "";
}

function same(field: FicheField, a: string, b: string): boolean {
  if (field === "year") return (Number(a.trim()) || 0) === (Number(b.trim()) || 0);
  return a.trim().split(/\s+/).join(" ") === b.trim().split(/\s+/).join(" ");
}

/** Le lot d'une fiche corrigée dans le panneau : ses champs changés, ou null. */
export function sheetLot(title: BankTitle, form: FicheForm): EditLot | null {
  const before = formOf(title);
  const values: Partial<FicheForm> = {};
  const expected: Partial<FicheForm> = {};
  for (const field of EDIT_FIELDS) {
    if (same(field, before[field], form[field])) continue;
    values[field] = form[field].trim();
    expected[field] = before[field];
  }
  return Object.keys(values).length ? { titles: [{ id: title.id, values, expected }] } : null;
}

/**
 * Le lot de « Modifier N fiches » : un champ coché prend la même valeur pour
 * tous les titres, un champ décoché garde celle de chacun.
 */
export function batchLot(titles: BankTitle[], checked: Partial<FicheForm>): EditLot {
  const fields = EDIT_FIELDS.filter((field) => checked[field] !== undefined);
  return {
    titles: titles.map((title) => {
      const before = formOf(title);
      const values: Partial<FicheForm> = {};
      const expected: Partial<FicheForm> = {};
      for (const field of fields) {
        values[field] = (checked[field] ?? "").trim();
        expected[field] = before[field];
      }
      return { id: title.id, values, expected };
    }),
  };
}

/** Le lot, sans les titres qui le refuseraient. */
export function withoutTitles(lot: EditLot, ids: Iterable<number>): EditLot {
  const gone = new Set(ids);
  return { titles: lot.titles.filter((entry) => !gone.has(entry.id)) };
}

function fiches(count: number): string {
  return count === 1 ? "1 fiche" : `${count} fiches`;
}

/** Ce qu'un essai dit des sélections de titres : « « Jazz » perd 12 titres. » */
export function selectionLines(selections: SelectionChange[]): string[] {
  return selections.map((change) => {
    const gained = titlesLabel(change.gained).toLowerCase();
    const lost = titlesLabel(change.lost).toLowerCase();
    if (change.gained && change.lost) return `« ${change.name} » gagne ${gained} et en perd ${change.lost}.`;
    if (change.gained) return `« ${change.name} » gagne ${gained}.`;
    return `« ${change.name} » perd ${lost}.`;
  });
}

/** Une ligne par titre en cause, cinq au plus, puis combien d'autres. */
export function issueLines(issues: TitleIssue[], max = 5): string[] {
  const lines = issues.slice(0, max).map((issue) => `${issue.label || `Titre ${issue.id}`} : ${issue.reason}`);
  if (issues.length > max) {
    const rest = issues.length - max;
    lines.push(rest === 1 ? "Et un autre titre." : `Et ${rest} autres titres.`);
  }
  return lines;
}

/** Le nom d'un titre dans un message : son titre, sinon son fichier. */
export function titleName(title: Pick<BankTitle, "title" | "path">): string {
  return title.title || fileName(title.path);
}

/**
 * Ce que dit la console après l'écriture. `name` : le titre, pour une fiche
 * corrigée seule.
 */
export function savedMessage(outcome: EditOutcome, name?: string): { text: string; tone: Tone } {
  const waiting = outcome.waiting.length;
  if (!outcome.written && !waiting) return { text: "Rien n'a changé : les fiches avaient déjà ces valeurs.", tone: "info" };
  if (name && outcome.written + waiting === 1) {
    return waiting
      ? { text: `La fiche de « ${name} » s'écrira quand le titre aura fini de passer à l'antenne.`, tone: "info" }
      : { text: `Fiche de « ${name} » corrigée.`, tone: "success" };
  }
  const parts: string[] = [];
  if (outcome.written) parts.push(`${fiches(outcome.written)} ${outcome.written === 1 ? "corrigée" : "corrigées"}.`);
  if (waiting) {
    const who = outcome.written ? (waiting === 1 ? "Une autre" : `${waiting} autres`) : waiting === 1 ? "Une fiche" : `${waiting} fiches`;
    parts.push(
      waiting === 1
        ? `${who} s'écrira quand son titre aura fini de passer à l'antenne.`
        : `${who} s'écriront quand leurs titres auront fini de passer à l'antenne.`,
    );
  }
  return { text: parts.join(" "), tone: outcome.written ? "success" : "info" };
}

/** Ce que dit la console après « Revenir ». */
export function undoneMessage(outcome: EditOutcome): { text: string; tone: Tone } {
  const kept = outcome.kept.length;
  const back = outcome.written
    ? `${fiches(outcome.written)} ${outcome.written === 1 ? "a repris sa" : "ont repris leurs"} ${outcome.written === 1 ? "valeur" : "valeurs"} d'avant.`
    : "Rien n'était encore écrit : le lot ne s'écrira pas.";
  if (!kept) return { text: back, tone: "success" };
  const changed =
    kept === 1
      ? "Un titre a gardé la sienne : sa fiche a changé depuis."
      : `${kept} titres ont gardé la leur : leurs fiches ont changé depuis.`;
  return { text: `${back} ${changed}`, tone: "info" };
}

/** Pourquoi un essai refuse d'écrire, en une phrase : le premier titre en cause. */
export function needsConfirmationText(outcome: EditOutcome): string {
  const first = outcome.refused[0];
  if (!first) return "";
  return `Rien n'a été écrit. ${first.reason}`;
}
