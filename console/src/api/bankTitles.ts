import type { TitleCart } from "./bankCarts.ts";
import type { BankShelf } from "./bankContent.ts";

/**
 * The bank's table (FON-64): every title of the Beets library, read by the
 * engine (`GET /media/titles.json`), ranged by collection, artist, family,
 * album or tag of the station (FON-74). Pure logic, tested alongside; the calls are in the components.
 */

/** A title of the library, as the engine's table gives it. */
export type BankTitle = {
  /** Its id in Beets: what the rundown, the fiches and the selections know. */
  id: number;
  title: string;
  artist: string;
  album: string;
  year: number | null;
  /** The genre written in the file. */
  genre: string;
  /** The short name of its family (`jazz`), empty until it is set. */
  famille: string;
  famille_label: string;
  /** The station's tags (FON-74), in the library only; absent from an older engine. */
  etiquettes?: string[];
  duration: number | null;
  zone: string;
  /** `rotation`, or the folder of its collection. */
  collection: string;
  /** Below the bank, as the station's folder shows it. */
  path: string;
  /** The fields of the fiche still empty. */
  missing: FicheField[];
  /** The carts that play it without a copy (FON-69); absent from an older engine. */
  carts?: TitleCart[];
};

export type FicheField = "title" | "artist" | "album" | "year" | "genre" | "famille";
export type BankFacet = { value: string; label: string; count: number };
export type Ranking = "collection" | "artist" | "famille" | "album" | "etiquette";
export type TitleSort = "title" | "artist" | "album" | "famille" | "genre" | "year" | "duration";
export type SortOrder = "asc" | "desc";

export type BankTitlesPage = {
  titles: BankTitle[];
  /** Every title of the library. */
  total: number;
  /** Those the filters keep. */
  matched: number;
  offset: number;
  limit: number;
  facets: Partial<Record<Ranking, BankFacet[]>>;
};

/** One page of the table. */
export const TITLES_PAGE = 100;

export const RANKINGS: Array<{ id: Ranking; label: string; plural: string; none: string }> = [
  { id: "collection", label: "Collection", plural: "Collections", none: "Hors collection" },
  { id: "artist", label: "Artiste", plural: "Artistes", none: "Sans artiste" },
  { id: "famille", label: "Famille", plural: "Familles", none: "Sans famille" },
  { id: "album", label: "Album", plural: "Albums", none: "Sans album" },
  { id: "etiquette", label: "Étiquette", plural: "Étiquettes", none: "Sans étiquette" },
];

export const FIELD_LABELS: Record<FicheField, string> = {
  title: "titre",
  artist: "artiste",
  album: "album",
  year: "année",
  genre: "genre",
  famille: "famille",
};

export type ColumnKey = TitleSort | "etiquettes" | "fiche";

/** The columns, in their own order; the tags and the fiche do not sort. */
export const COLUMNS: Array<{ key: ColumnKey; label: string }> = [
  { key: "title", label: "Titre" },
  { key: "artist", label: "Artiste" },
  { key: "album", label: "Album" },
  { key: "famille", label: "Famille" },
  { key: "etiquettes", label: "Étiquettes" },
  { key: "genre", label: "Genre" },
  { key: "year", label: "Année" },
  { key: "duration", label: "Durée" },
  { key: "fiche", label: "Fiche" },
];

const SORTS = new Set<string>(["title", "artist", "album", "famille", "genre", "year", "duration"]);

export function isRanking(value: string | null): value is Ranking {
  return RANKINGS.some((item) => item.id === value);
}

export function isSort(value: string | null): value is TitleSort {
  return value != null && SORTS.has(value);
}

/**
 * What an engine before FON-74 does not know: the tags, as a ranking and a column.
 * The console hides them rather than ask for them.
 */
export function rankingsFor(tags: boolean): Ranking[] {
  return RANKINGS.map((item) => item.id).filter((id) => tags || id !== "etiquette");
}

export function columnsFor(columns: ColumnKey[], tags: boolean): ColumnKey[] {
  return tags ? columns : columns.filter((key) => key !== "etiquettes");
}

export function rankingOf(id: Ranking) {
  return RANKINGS.find((item) => item.id === id) ?? RANKINGS[0];
}

/** What the table shows: a ranking, one of its groups or the whole bank (null), a text, an order, its columns. */
export type TableState = {
  ranking: Ranking;
  /** null: the whole bank. An empty value: the titles where that field is empty. */
  group: string | null;
  q: string;
  sort: TitleSort;
  order: SortOrder;
  /** Shown, in this order; the title always is. */
  columns: ColumnKey[];
};

export const DEFAULT_COLUMNS: ColumnKey[] = COLUMNS.map((column) => column.key);

export const DEFAULT_STATE: TableState = {
  ranking: "collection",
  group: null,
  q: "",
  sort: "artist",
  order: "asc",
  columns: DEFAULT_COLUMNS,
};

/** Columns read from anywhere: known ones once each, the title always. */
export function cleanColumns(raw: unknown): ColumnKey[] {
  if (!Array.isArray(raw)) return DEFAULT_COLUMNS;
  const known = new Set<string>(DEFAULT_COLUMNS);
  const kept: ColumnKey[] = [];
  for (const item of raw) {
    if (typeof item === "string" && known.has(item) && !kept.includes(item as ColumnKey)) kept.push(item as ColumnKey);
  }
  return kept.includes("title") ? kept : ["title", ...kept];
}

function sameColumns(a: ColumnKey[], b: ColumnKey[]): boolean {
  return a.length === b.length && a.every((key, index) => key === b[index]);
}

/** Shows or hides a column; the title stays. A column shown again goes back at its own place. */
export function toggleColumn(columns: ColumnKey[], key: ColumnKey): ColumnKey[] {
  if (key === "title") return columns;
  if (columns.includes(key)) return columns.filter((item) => item !== key);
  const rank = (item: ColumnKey) => DEFAULT_COLUMNS.indexOf(item);
  const next = [...columns];
  const after = next.findIndex((item) => rank(item) > rank(key));
  next.splice(after < 0 ? next.length : after, 0, key);
  return next;
}

/** Moves a shown column one place up (-1) or down (+1). */
export function moveColumn(columns: ColumnKey[], key: ColumnKey, delta: -1 | 1): ColumnKey[] {
  const index = columns.indexOf(key);
  const target = index + delta;
  if (index < 0 || target < 0 || target >= columns.length) return columns;
  const next = [...columns];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

// The room each column takes, in rem, as sons.css gives it; the title at least 12.
const COLUMN_REM: Record<ColumnKey, number> = {
  title: 12,
  artist: 10,
  album: 9.5,
  famille: 7,
  etiquettes: 9,
  genre: 7,
  year: 4,
  duration: 4.25,
  fiche: 7.5,
};

/** Under this width the table scrolls sideways, as a spreadsheet: the play button, the columns, the gestures. */
export function tableMinWidth(columns: ColumnKey[], gestures: boolean): number {
  const shown = columns.reduce((total, key) => total + COLUMN_REM[key], 0);
  return Math.round((2.9 + shown + (gestures ? 6.35 : 0)) * 100) / 100;
}

export function columnLabel(key: ColumnKey): string {
  return COLUMNS.find((column) => column.key === key)?.label ?? key;
}

/**
 * The table's state, read from the address: `?ranger=artist&groupe=Orage&tri=year&ordre=desc`.
 * A link to a collection of the former view (`?collection=jazz`) still opens it.
 */
export function readState(params: URLSearchParams): TableState {
  const ranking = isRanking(params.get("ranger")) ? (params.get("ranger") as Ranking) : "collection";
  let group = params.has("groupe") ? (params.get("groupe") ?? "") : null;
  if (group === null && ranking === "collection" && params.get("collection")) group = params.get("collection");
  const sort = isSort(params.get("tri")) ? (params.get("tri") as TitleSort) : DEFAULT_STATE.sort;
  const order: SortOrder = params.get("ordre") === "desc" ? "desc" : "asc";
  const columns = params.has("colonnes") ? cleanColumns((params.get("colonnes") ?? "").split(",")) : DEFAULT_COLUMNS;
  return { ranking, group, q: params.get("q") ?? "", sort, order, columns };
}

/** The address of a state, keeping the other parameters (the view of the bank). */
export function writeState(params: URLSearchParams, state: TableState): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of ["ranger", "groupe", "collection", "tri", "ordre", "q", "colonnes"]) next.delete(key);
  if (state.ranking !== DEFAULT_STATE.ranking) next.set("ranger", state.ranking);
  if (state.group !== null) next.set("groupe", state.group);
  if (state.sort !== DEFAULT_STATE.sort) next.set("tri", state.sort);
  if (state.order !== DEFAULT_STATE.order) next.set("ordre", state.order);
  if (state.q.trim()) next.set("q", state.q);
  if (!sameColumns(state.columns, DEFAULT_COLUMNS)) next.set("colonnes", state.columns.join(","));
  return next;
}

/** A view an account keeps under a name (FON-65), as the engine gives it. */
export type SavedView = { id: number; name: string; state: Partial<TableState>; modified: string | null };

/** What a view keeps of the table. */
export function viewStateOf(state: TableState): TableState {
  return { ...state, q: state.q.trim() };
}

/** The table a view opens, whatever an older or a hand-written view lacks. */
export function stateOfView(view: SavedView): TableState {
  const kept = view.state ?? {};
  return {
    ranking: isRanking(kept.ranking ?? null) ? (kept.ranking as Ranking) : DEFAULT_STATE.ranking,
    group: typeof kept.group === "string" ? kept.group : null,
    q: typeof kept.q === "string" ? kept.q : "",
    sort: isSort(kept.sort ?? null) ? (kept.sort as TitleSort) : DEFAULT_STATE.sort,
    order: kept.order === "desc" ? "desc" : "asc",
    columns: cleanColumns(kept.columns),
  };
}

/** Whether the table still shows what the view keeps. */
export function sameAsView(state: TableState, view: SavedView): boolean {
  const kept = stateOfView(view);
  const shown = viewStateOf(state);
  return (
    kept.ranking === shown.ranking &&
    kept.group === shown.group &&
    kept.q === shown.q &&
    kept.sort === shown.sort &&
    kept.order === shown.order &&
    sameColumns(kept.columns, shown.columns)
  );
}

/** The name typed for a view, as the engine keeps it; or why it is refused. */
export function viewNameProblem(name: string, views: SavedView[], own: number | null = null): string {
  const clean = name.trim().replace(/\s+/g, " ");
  if (!clean) return "Donne un nom à la vue.";
  if (clean.length > 60) return "Un nom de vue tient en 60 signes.";
  if (views.some((view) => view.name === clean && view.id !== own)) return `Tu as déjà une vue « ${clean} ».`;
  return "";
}

/** The query of `/media/titles.json` for a state and a page; with the facets of its ranking. */
export function titlesQuery(state: TableState, offset = 0, limit = TITLES_PAGE): string {
  const params = new URLSearchParams();
  if (state.q.trim()) params.set("q", state.q.trim());
  if (state.group !== null) params.set(state.ranking, state.group);
  params.set("sort", state.sort);
  params.set("order", state.order);
  if (offset) params.set("offset", String(offset));
  params.set("limit", String(limit));
  params.set("facets", state.ranking);
  return `?${params.toString()}`;
}

/** A click on a column: its order, then the other way. Year and duration start with the largest. */
export function nextSort(state: TableState, key: TitleSort): Pick<TableState, "sort" | "order"> {
  if (state.sort === key) return { sort: key, order: state.order === "asc" ? "desc" : "asc" };
  return { sort: key, order: key === "year" || key === "duration" ? "desc" : "asc" };
}

/**
 * The groups of the left column. Ranged by collection, every collection the
 * catalogue knows is there, even empty, with its name: rotation first.
 */
export function groupsOf(ranking: Ranking, facets: BankFacet[], shelves: BankShelf[]): BankFacet[] {
  if (ranking !== "collection") return facets;
  const counts = new Map(facets.map((facet) => [facet.value, facet.count]));
  const known = shelves.map((shelf) => ({ value: shelf.id, label: shelf.label, count: counts.get(shelf.id) ?? 0 }));
  const strays = facets.filter((facet) => facet.value && !shelves.some((shelf) => shelf.id === facet.value));
  const none = facets.filter((facet) => !facet.value);
  return [...known.sort((a, b) => Number(b.value === "rotation") - Number(a.value === "rotation")), ...strays, ...none];
}

function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLocaleLowerCase("fr");
}

/** The groups whose name holds every word typed. */
export function filterGroups(groups: BankFacet[], query: string, ranking: Ranking): BankFacet[] {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (!words.length) return groups;
  return groups.filter((group) => {
    const name = fold(groupLabel(ranking, group.value, groups));
    return words.every((word) => name.includes(word));
  });
}

/** The name of a group, as the left column and the head of the table say it. */
export function groupLabel(ranking: Ranking, value: string | null, groups: BankFacet[]): string {
  if (value === null) return "Toute la banque";
  if (!value) return rankingOf(ranking).none;
  return groups.find((group) => group.value === value)?.label || value;
}

export function titlesCount(count: number): string {
  if (count === 0) return "Aucun titre";
  return `${count.toLocaleString("fr-FR")} titre${count > 1 ? "s" : ""}`;
}

/** The Fiche column: complete, or what is left to fill. */
export function ficheState(missing: FicheField[]): { complete: boolean; label: string; detail: string } {
  if (!missing.length) return { complete: true, label: "Complète", detail: "Tous les champs de la fiche sont remplis." };
  const names = missing.map((field) => FIELD_LABELS[field]);
  const list = names.length > 1 ? `${names.slice(0, -1).join(", ")} et ${names[names.length - 1]}` : names[0];
  return {
    complete: false,
    label: missing.length === 1 ? "1 champ vide" : `${missing.length} champs vides`,
    detail: `${list[0].toUpperCase()}${list.slice(1)} à remplir.`,
  };
}

/** A title's name below its collection's folder: what the catalogue takes back to move or remove it. */
export function nameInShelf(title: Pick<BankTitle, "path">, shelf: Pick<BankShelf, "folder">): string | null {
  const folder = shelf.folder.replace(/\/+$/, "");
  if (!folder || !title.path.startsWith(`${folder}/`)) return null;
  return title.path.slice(folder.length + 1);
}

/** The file's name, the last part of its path. */
export function fileName(path: string): string {
  return path.split("/").pop() || path;
}

/** Shown in a cell: a dash for what is empty. */
export function cell(value: string | number | null | undefined): string {
  if (value == null || value === "") return "—";
  return String(value);
}
