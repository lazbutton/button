import type { TableState } from "./bankTitles.ts";

/**
 * A selection of titles composed by filters (FON-73). The console keeps the
 * filters; the engine writes the Beets query that says the same
 * (`GET /media/selection.json`), and counts it as the table does.
 */
export type SelectionFilters = {
  famille: string;
  collection: string;
  artist: string;
  album: string;
  genre: string;
  /** A tag of the station (FON-74): that tag alone, not « minuit » for « nuit ». */
  etiquette: string;
  year_from: string;
  year_to: string;
};

export const NO_FILTERS: SelectionFilters = {
  famille: "",
  collection: "",
  artist: "",
  album: "",
  genre: "",
  etiquette: "",
  year_from: "",
  year_to: "",
};

const KEYS = Object.keys(NO_FILTERS) as Array<keyof SelectionFilters>;

/** What the engine answers: the query, how many titles it takes, ten of them. */
export type ComposedSelection = { query: string; count: number; sample: Array<{ artist: string; title: string }> };

export function hasFilter(filters: SelectionFilters): boolean {
  return KEYS.some((key) => filters[key].trim() !== "");
}

/** A year typed: four digits, or nothing. */
export function yearProblem(value: string): string {
  const text = value.trim();
  if (!text) return "";
  return /^\d{4}$/.test(text) ? "" : "Une année s'écrit en quatre chiffres.";
}

export function filtersProblem(filters: SelectionFilters): string {
  const year = yearProblem(filters.year_from) || yearProblem(filters.year_to);
  if (year) return year;
  if (filters.year_from.trim() && filters.year_to.trim() && Number(filters.year_from) > Number(filters.year_to)) {
    return "L'année de début vient après celle de fin.";
  }
  return "";
}

/** The query string of `/media/selection.json`, and of the table counting the same. */
export function filtersQuery(filters: SelectionFilters): string {
  const params = new URLSearchParams();
  for (const key of KEYS) {
    const value = filters[key].trim();
    if (value) params.set(key, value);
  }
  return params.toString();
}

/** A ranking the composer knows: the verdict (FON-80) is not one of its filters. */
function composable(ranking: TableState["ranking"]): ranking is TableState["ranking"] & keyof SelectionFilters {
  return (KEYS as string[]).includes(ranking);
}

/** The filters of a group of the table: « Créer une sélection » takes them. */
export function filtersFromTable(state: Pick<TableState, "ranking" | "group">): SelectionFilters {
  const filters = { ...NO_FILTERS };
  if (state.group && composable(state.ranking)) filters[state.ranking] = state.group;
  return filters;
}

/** Whether the table's group can become a selection: a group with a value, of a ranking the composer knows. */
export function tableMakesSelection(state: Pick<TableState, "ranking" | "group">): boolean {
  return Boolean(state.group) && composable(state.ranking);
}

/** Where « Créer une sélection » leads: the selections, the new one open with these filters. */
export function selectionLink(filters: SelectionFilters): string {
  const query = filtersQuery(filters);
  return `/programmation?onglet=categories&nouvelle-selection=1${query ? `&${query}` : ""}`;
}

/** The filters a link carries, and whether it asks for a new selection. */
export function filtersFromParams(params: URLSearchParams): SelectionFilters | null {
  if (params.get("nouvelle-selection") !== "1") return null;
  const filters = { ...NO_FILTERS };
  for (const key of KEYS) filters[key] = params.get(key) ?? "";
  return filters;
}

/** The address once the dialog took the link's filters: they do not open it again. */
export function withoutSelectionParams(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params);
  next.delete("nouvelle-selection");
  for (const key of KEYS) next.delete(key);
  return next;
}

/**
 * A name to start from: « Jazz depuis 2015 · Nuit ». `labels` names a family or
 * a collection as the console shows it.
 */
export function suggestedName(
  filters: SelectionFilters,
  labels: { famille?: (value: string) => string; collection?: (value: string) => string } = {},
): string {
  const parts: string[] = [];
  const head = [
    filters.famille ? (labels.famille?.(filters.famille) ?? filters.famille) : "",
    filters.genre.trim(),
    filters.artist.trim(),
    filters.album.trim(),
    filters.etiquette.trim(),
  ].filter(Boolean);
  if (head.length) parts.push(head.join(", "));
  const from = filters.year_from.trim();
  const to = filters.year_to.trim();
  if (from && to) parts.push(from === to ? `en ${from}` : `de ${from} à ${to}`);
  else if (from) parts.push(`depuis ${from}`);
  else if (to) parts.push(`jusqu'à ${to}`);
  const first = parts.join(" ");
  const collection = filters.collection ? (labels.collection?.(filters.collection) ?? filters.collection) : "";
  const name = [first, collection].filter(Boolean).join(" · ");
  return name ? name[0].toUpperCase() + name.slice(1) : "";
}
