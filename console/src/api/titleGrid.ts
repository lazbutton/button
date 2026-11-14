import type { BankTitle, FicheField } from "./bankTitles.ts";
import { EDIT_LABELS, batchLot, formOf, yearProblem, type EditLot } from "./titleEdits.ts";

/**
 * Corriger comme dans un tableur (FON-67) : les cellules du tableau de la banque
 * qui s'ouvrent au clavier, où l'on passe de l'une à l'autre, et ce qu'un
 * collage écrit. L'écriture passe par le lot de FON-66 (titleEdits.ts). Sans React.
 *
 * Le titre reste le bouton qui ouvre la fiche : il se corrige dans le panneau.
 */

/** Les colonnes qui s'ouvrent, dans l'ordre du tableau. */
export const GRID_FIELDS: FicheField[] = ["artist", "album", "famille", "genre", "year"];

export function isGridField(key: string): key is FicheField {
  return (GRID_FIELDS as string[]).includes(key);
}

/** Ce que la cellule contient, en texte : la famille par son nom court. */
export function cellText(title: BankTitle, field: FicheField): string {
  return formOf(title)[field];
}

/** « Album de « Comète » » : le nom d'une cellule, pour un lecteur d'écran. */
export function cellName(field: FicheField, name: string): string {
  return `${EDIT_LABELS[field]} de « ${name} »`;
}

export type Move = "up" | "down" | "left" | "right" | "next" | "previous";

/** La touche qui déplace d'une cellule à l'autre, ou null. */
export function moveOf(key: string, shift: boolean): Move | null {
  switch (key) {
    case "ArrowUp":
      return "up";
    case "ArrowDown":
      return "down";
    case "ArrowLeft":
      return "left";
    case "ArrowRight":
      return "right";
    case "Tab":
      return shift ? "previous" : "next";
    default:
      return null;
  }
}

/**
 * La cellule où mène un déplacement, ou null au bord du tableau. `row` est le
 * rang du titre, `column` celui de la colonne parmi celles qui s'ouvrent. Tab
 * passe à la colonne suivante, puis à la première du titre suivant.
 */
export function nextCell(
  at: { row: number; column: number },
  move: Move,
  rows: number,
  columns: number,
): { row: number; column: number } | null {
  let { row, column } = at;
  if (move === "up") row -= 1;
  else if (move === "down") row += 1;
  else if (move === "left") column -= 1;
  else if (move === "right") column += 1;
  else if (move === "next") {
    column += 1;
    if (column >= columns) {
      column = 0;
      row += 1;
    }
  } else {
    column -= 1;
    if (column < 0) {
      column = columns - 1;
      row -= 1;
    }
  }
  if (row < 0 || row >= rows || column < 0 || column >= columns) return null;
  return { row, column };
}

/** Le lot d'une cellule enregistrée : ce titre, ce champ, ce que la cellule montrait. */
export function cellLot(title: BankTitle, field: FicheField, value: string): EditLot | null {
  const before = cellText(title, field);
  if (before.trim().split(/\s+/).join(" ") === value.trim().split(/\s+/).join(" ")) return null;
  return { titles: [{ id: title.id, values: { [field]: value.trim() }, expected: { [field]: before } }] };
}

/**
 * Ce qu'un collage écrit : une seule valeur, sur un champ, pour les titres
 * sélectionnés, ou ce qui l'empêche.
 */
export function pasteLot(
  titles: BankTitle[],
  field: FicheField,
  text: string,
): { lot: EditLot; value: string } | { problem: string } {
  const lines = text.replace(/\r\n?/g, "\n").replace(/\n+$/, "").split("\n");
  if (lines.length > 1) return { problem: "Un collage écrit une seule valeur : copie une seule cellule à la fois." };
  const value = lines[0].replace(/\t/g, " ").trim();
  if (field === "year") {
    const problem = yearProblem(value);
    if (problem) return { problem };
  }
  if (field === "famille" && value) return { problem: "La famille se choisit dans sa liste, cellule par cellule." };
  return { lot: batchLot(titles, { [field]: value }), value };
}

const ARTICLES: Record<FicheField, string> = {
  title: "le ",
  artist: "l'",
  album: "l'",
  year: "l'",
  genre: "le ",
  famille: "la ",
};

/** La question avant d'écrire un collage : « Écrire « Ciel » dans l'album de 30 titres ? » */
export function pasteQuestion(field: FicheField, value: string, count: number): string {
  const what = EDIT_LABELS[field].toLowerCase();
  const article = ARTICLES[field];
  const titles = count === 1 ? "1 titre" : `${count} titres`;
  return value
    ? `Écrire « ${value} » dans ${article}${what} de ${titles} ?`
    : `Vider ${article}${what} de ${titles} ?`;
}
