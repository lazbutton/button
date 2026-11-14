import { parseTags } from "./stationTags.ts";
import { EDIT_LABELS } from "./titleEdits.ts";
import { formatWhen } from "./updates.ts";

/**
 * Le journal des gestes sur la banque et les bacs (FON-71) : ce que rend
 * `GET /media/journal.json`, et ce que la page Journal en dit. Sans React.
 */

export const JOURNAL_JSON = "/media/journal.json";

export type JournalCounts = {
  done: number;
  waiting: number;
  kept: number;
  cancelled: number;
  failed: number;
  pending: number;
};

export type JournalEntry = {
  id: number;
  gesture: string;
  gesture_label: string;
  username: string;
  /** À l'heure de Paris, avec son décalage. */
  created: string;
  titles: number;
  fields: string[];
  undo_of: number | null;
  undone_by: { id: number; username: string; created: string } | null;
  undoable: boolean;
  why_not: string | null;
  counts: JournalCounts;
};

export type JournalChange = {
  id: number | null;
  label: string;
  path: string;
  field: string;
  old: unknown;
  new: unknown;
  status: string;
  reason: string | null;
};

export type JournalFacet = { value: string; label?: string; count: number };

export type JournalPage = {
  entries: JournalEntry[];
  /** Le lot après lequel reprendre, ou null : tout est là. */
  next: number | null;
  gestures: JournalFacet[];
  people: JournalFacet[];
  undo_days: number;
};

export type JournalDetail = JournalEntry & { changes: JournalChange[] };

/** Les filtres de la page, dans l'adresse de la route. */
export function journalQuery(filters: { gesture: string; username: string }, before?: number | null): string {
  const params = new URLSearchParams();
  if (filters.gesture) params.set("gesture", filters.gesture);
  if (filters.username) params.set("username", filters.username);
  if (before != null) params.set("before", String(before));
  const query = params.toString();
  return query ? `?${query}` : "";
}

// Ce que nomment les gestes à venir : un renommage ou un déplacement change le fichier.
const OTHER_FIELDS: Record<string, string> = { path: "fichier", label: "label", isrc: "ISRC", etiquettes: "étiquettes" };

// Ce que notent les gestes sur les bacs : le bac d'un son, son rang.
const CART_FIELDS = new Set(["cart", "rank"]);

function fieldName(field: string): string {
  return (EDIT_LABELS as Record<string, string>)[field]?.toLowerCase() ?? OTHER_FIELDS[field] ?? field;
}

function list(names: string[]): string {
  if (names.length < 2) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} et ${names[names.length - 1]}`;
}

/** « Correction de 38 titres : l'album et l'année. » */
export function entryTitle(entry: Pick<JournalEntry, "gesture_label" | "titles" | "fields">): string {
  const titles = entry.titles === 1 ? "1 titre" : `${entry.titles} titres`;
  // Un geste sur les bacs (FON-70) dit ses bacs dans son nom, pas ses champs.
  const fields = entry.fields.filter((field) => !CART_FIELDS.has(field)).map(fieldName);
  return fields.length ? `${entry.gesture_label} de ${titles} : ${list(fields)}` : `${entry.gesture_label} de ${titles}`;
}

/** « par programmatrice, aujourd’hui à 14:02 » */
export function entryByline(entry: Pick<JournalEntry, "username" | "created">, now?: Date): string {
  return `par ${entry.username}, ${formatWhen(entry.created, now)}`;
}

/**
 * Ce qui reste à dire d'un lot, au-delà de ce qui est écrit : ce qui attend, ce
 * qui a gardé sa valeur, ce qui a échoué ou été annulé avant de s'écrire.
 */
export function entryNotes(counts: JournalCounts): string[] {
  const notes: string[] = [];
  const titles = (count: number) => (count === 1 ? "1 titre" : `${count} titres`);
  if (counts.waiting) notes.push(`${titles(counts.waiting)} en attente de la fin d'un passage à l'antenne`);
  if (counts.kept) notes.push(`${titles(counts.kept)} ${counts.kept === 1 ? "a gardé sa" : "ont gardé leur"} valeur`);
  if (counts.cancelled) notes.push(`${titles(counts.cancelled)} jamais ${counts.cancelled === 1 ? "écrit" : "écrits"}`);
  if (counts.failed) notes.push(`${titles(counts.failed)} en échec`);
  return notes;
}

/** Ce qu'une annulation défera, dit avant de la confirmer. */
export function undoQuestion(entry: Pick<JournalEntry, "titles" | "counts">): string {
  const back =
    entry.titles === 1
      ? "Le titre reprend sa valeur d'avant, sauf si elle a changé depuis."
      : `Les ${entry.titles} titres reprennent leurs valeurs d'avant, sauf celles qui ont changé depuis.`;
  return entry.counts.waiting ? `${back} Ce qui attend encore ne s'écrira pas.` : back;
}

/** Une valeur d'avant ou d'après, telle qu'une personne la lit : les étiquettes, une par une. */
export function changeValue(value: unknown, field = ""): string {
  if (value === null || value === undefined || value === "" || value === 0) return "vide";
  if (field === "etiquettes") return parseTags(String(value)).join(", ") || "vide";
  return String(value);
}

export const STATUS_LABELS: Record<string, string> = {
  done: "écrit",
  waiting: "en attente",
  kept: "gardé",
  cancelled: "jamais écrit",
  failed: "en échec",
  pending: "en cours",
};

export function changeField(field: string): string {
  const name = fieldName(field);
  return name.charAt(0).toUpperCase() + name.slice(1);
}
