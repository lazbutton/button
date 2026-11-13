import { displayNow } from "../lib/nowPlaying.ts";
import { LEGACY_TAB_QUERY, legacyIsRotationFolder } from "./legacyLayout.ts";

export type LibraryHit = {
  id: string;
  path: string;
  filename?: string;
  title: string;
  artist: string;
  kind: string;
  grouping?: string;
  folder?: string;
  /** Où est le titre : rotation, collections, habillage, emissions ou bacs. Absent d'un catalogue plus ancien. */
  zone?: string;
  /** Le dossier d'habillage du titre, comme beds ; vide ailleurs. Absent d'un catalogue plus ancien. */
  habillage?: string;
  duration: number;
};

export type LibrarySearchResponse = {
  hits: LibraryHit[];
  estimatedTotalHits?: number;
  /** Les filtres que le catalogue a pris. Absent d'un catalogue plus ancien. */
  filters?: string[];
  error?: string;
};

export type LibraryTabId =
  | "all"
  | "musique"
  | "jingle"
  | "pub"
  | "habillage"
  | "archives"
  | "emission";

export const LIBRARY_TABS: { id: LibraryTabId; label: string }[] = [
  { id: "all", label: "Tous" },
  { id: "musique", label: "Musique" },
  { id: "jingle", label: "Jingles" },
  { id: "pub", label: "Pubs" },
  { id: "habillage", label: "Habillage" },
  { id: "archives", label: "Collections" },
  { id: "emission", label: "Émissions" },
];

/** What each tab asks the catalogue: no folder of the bank is named. */
export const TAB_QUERY: Record<LibraryTabId, Record<string, string>> = {
  all: {},
  musique: { grouping: "rotation" },
  jingle: { kind: "jingle" },
  pub: { kind: "pub" },
  habillage: { zone: "habillage", habillage: "beds,stings,sfx" },
  // Every collection, the ones created later too.
  archives: { zone: "collections" },
  emission: { kind: "emission" },
};

export const LIBRARY_DRAG_MIME = "application/x-button-library";

export function labelsFromHit(hit: LibraryHit): { artist: string; title: string } {
  const parsed = displayNow({
    title: hit.title || hit.filename || hit.path,
    artist: hit.artist || "",
  });
  return {
    artist: parsed.artist,
    title: parsed.title || hit.title || hit.filename || hit.path,
  };
}

export function deskKindFromHit(hit: LibraryHit): "musique" | "jingle" | "son" | "pub" {
  if (hit.kind === "jingle" || hit.kind === "pub") return hit.kind;
  if (hit.grouping === "rotation" || hit.zone === "rotation") return "musique";
  if (hit.zone === undefined && legacyIsRotationFolder(hit.folder)) return "musique";
  return "son";
}

/**
 * The filters of a tab the catalogue did not take: an older catalogue ignores `zone`,
 * and answers every title. Such a search is asked again, by folder.
 */
export function legacyRetry(tab: LibraryTabId, filters: string[] | undefined): Record<string, string> | null {
  const legacy = LEGACY_TAB_QUERY[tab];
  if (!legacy || filters !== undefined) return null;
  return legacy;
}

async function searchOnce(q: string, limit: number, extra: Record<string, string>): Promise<LibrarySearchResponse> {
  const search = new URLSearchParams();
  search.set("q", q);
  search.set("limit", String(limit));
  for (const [key, value] of Object.entries(extra)) search.set(key, value);
  let response: Response;
  try {
    response = await fetch(`/library/search?${search}`, { cache: "no-store" });
  } catch {
    throw new Error("Catalogue injoignable.");
  }
  const payload = (await response.json().catch(() => ({}))) as LibrarySearchResponse;
  if (response.status === 401) throw new Error("Session expirée : recharge la page et reconnecte-toi.");
  if (!response.ok) {
    throw new Error(payload.error?.trim() || "Recherche catalogue impossible.");
  }
  return {
    hits: Array.isArray(payload.hits) ? payload.hits : [],
    estimatedTotalHits: payload.estimatedTotalHits,
    filters: Array.isArray(payload.filters) ? payload.filters : undefined,
  };
}

export async function librarySearch(params: {
  q: string;
  tab: LibraryTabId;
  limit?: number;
}): Promise<LibrarySearchResponse> {
  const limit = params.limit ?? 40;
  const answer = await searchOnce(params.q, limit, TAB_QUERY[params.tab]);
  const legacy = legacyRetry(params.tab, answer.filters);
  const found = legacy ? await searchOnce(params.q, limit, legacy) : answer;
  return { hits: found.hits, estimatedTotalHits: found.estimatedTotalHits };
}
