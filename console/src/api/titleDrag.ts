import type { FicheField, Ranking } from "./bankTitles.ts";

/**
 * Titles of the bank's table dragged onto a group of its left column (FON-75):
 * what the drop does. The same gestures stay in the selection bar, for the
 * keyboard and the phone, where nothing is dragged. Pure logic, tested alongside.
 */

/** The type of the data a drag of titles carries: their ids, as JSON. */
export const TITLES_TYPE = "application/x-button-titles";

/** The titles a drag takes: the selection when the row is in it, else the row alone. */
export function draggedIds(rowId: number, selected: ReadonlySet<number>): number[] {
  return selected.has(rowId) ? [...selected] : [rowId];
}

export function encodeIds(ids: number[]): string {
  return JSON.stringify(ids);
}

/** The ids a drop carries; none when it is not a drag of titles. */
export function decodeIds(raw: string): number[] {
  try {
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((id): id is number => Number.isInteger(id)) : [];
  } catch {
    return [];
  }
}

export type DropAction =
  | { kind: "move"; from: string; to: string }
  | { kind: "edit"; field: FicheField; value: string }
  | { kind: "refuse"; reason: string };

const FIELDS: Partial<Record<Ranking, FicheField>> = { artist: "artist", album: "album", famille: "famille" };

/** Whether a group of the left column takes titles: a group with a value. */
export function takesTitles(ranking: Ranking, value: string | null): boolean {
  return value != null && value !== "" && (ranking === "collection" || ranking in FIELDS);
}

/**
 * What titles dropped on a group do. On a collection, they move there, all from
 * one collection; on an artist, an album or a family, their fiches take it,
 * after the confirmation of the lot.
 */
export function dropAction(
  ranking: Ranking,
  value: string,
  label: string,
  titles: Array<{ collection: string }>,
): DropAction {
  if (!titles.length) return { kind: "refuse", reason: "Rien à déposer." };
  if (!takesTitles(ranking, value)) {
    return { kind: "refuse", reason: "Dépose les titres sur un groupe qui a un nom : un champ ne se vide pas ainsi." };
  }
  if (ranking === "collection") {
    const from = [...new Set(titles.map((title) => title.collection))];
    if (from.length === 1 && from[0] === value) {
      return { kind: "refuse", reason: `Ces titres sont déjà dans « ${label} ».` };
    }
    if (from.length > 1 || !from[0]) {
      return {
        kind: "refuse",
        reason: "Ces titres viennent de plusieurs collections : déplace-les une collection à la fois.",
      };
    }
    return { kind: "move", from: from[0], to: value };
  }
  return { kind: "edit", field: FIELDS[ranking] as FicheField, value };
}

/** What the group says while titles hover over it. */
export function dropHint(ranking: Ranking, label: string): string {
  if (ranking === "collection") return `Déposer pour déplacer vers « ${label} »`;
  const field = ranking === "artist" ? "l'artiste" : ranking === "album" ? "l'album" : "la famille";
  return `Déposer pour leur donner ${field} « ${label} »`;
}
