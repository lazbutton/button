import type { BankShelf } from "./bankContent.ts";

/**
 * The bank's table (FON-64): every title of the Beets library, read by the
 * engine (`GET /media/titles.json`), ranged by collection, artist, family or
 * album. Pure logic, tested alongside; the calls are in the components.
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
  duration: number | null;
  zone: string;
  /** `rotation`, or the folder of its collection. */
  collection: string;
  /** Below the bank, as the station's folder shows it. */
  path: string;
  /** The fields of the fiche still empty. */
  missing: FicheField[];
};

export type FicheField = "title" | "artist" | "album" | "year" | "genre" | "famille";
export type BankFacet = { value: string; label: string; count: number };
export type Ranking = "collection" | "artist" | "famille" | "album";
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
];

export const FIELD_LABELS: Record<FicheField, string> = {
  title: "titre",
  artist: "artiste",
  album: "album",
  year: "année",
  genre: "genre",
  famille: "famille",
};

/** The columns, in order; the last one, the fiche, does not sort. */
export const COLUMNS: Array<{ key: TitleSort | "fiche"; label: string }> = [
  { key: "title", label: "Titre" },
  { key: "artist", label: "Artiste" },
  { key: "album", label: "Album" },
  { key: "famille", label: "Famille" },
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

export function rankingOf(id: Ranking) {
  return RANKINGS.find((item) => item.id === id) ?? RANKINGS[0];
}

/** What the table shows: a ranking, one of its groups or the whole bank (null), a text, an order. */
export type TableState = {
  ranking: Ranking;
  /** null: the whole bank. An empty value: the titles where that field is empty. */
  group: string | null;
  q: string;
  sort: TitleSort;
  order: SortOrder;
};

export const DEFAULT_STATE: TableState = { ranking: "collection", group: null, q: "", sort: "artist", order: "asc" };

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
  return { ranking, group, q: params.get("q") ?? "", sort, order };
}

/** The address of a state, keeping the other parameters (the view of the bank). */
export function writeState(params: URLSearchParams, state: TableState): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of ["ranger", "groupe", "collection", "tri", "ordre", "q"]) next.delete(key);
  if (state.ranking !== DEFAULT_STATE.ranking) next.set("ranger", state.ranking);
  if (state.group !== null) next.set("groupe", state.group);
  if (state.sort !== DEFAULT_STATE.sort) next.set("tri", state.sort);
  if (state.order !== DEFAULT_STATE.order) next.set("ordre", state.order);
  if (state.q.trim()) next.set("q", state.q);
  return next;
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
