import { displayNow } from "../lib/nowPlaying";

export type LibraryHit = {
  id: string;
  path: string;
  filename?: string;
  title: string;
  artist: string;
  kind: string;
  grouping?: string;
  folder?: string;
  duration: number;
};

export type LibrarySearchResponse = {
  hits: LibraryHit[];
  estimatedTotalHits?: number;
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
  { id: "archives", label: "Archives" },
  { id: "emission", label: "Émissions" },
];

const TAB_QUERY: Record<LibraryTabId, Record<string, string>> = {
  all: {},
  musique: { grouping: "rotation" },
  jingle: { kind: "jingle" },
  pub: { kind: "pub" },
  habillage: { folder: "30-habillage/beds,30-habillage/stings,30-habillage/sfx" },
  // Every bank of 20-archives, the ones created later too.
  archives: { top: "20-archives" },
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
  const folder = hit.folder || "";
  const grouping = hit.grouping || "";
  if (grouping === "rotation" || folder.startsWith("10-rotation")) return "musique";
  return "son";
}

export async function librarySearch(params: {
  q: string;
  tab: LibraryTabId;
  limit?: number;
}): Promise<LibrarySearchResponse> {
  const search = new URLSearchParams();
  search.set("q", params.q);
  search.set("limit", String(params.limit ?? 40));
  const extra = TAB_QUERY[params.tab];
  for (const [key, value] of Object.entries(extra)) search.set(key, value);
  let response: Response;
  try {
    response = await fetch(`/library/search?${search}`, { cache: "no-store" });
  } catch {
    throw new Error("Catalogue injoignable.");
  }
  const payload = (await response.json().catch(() => ({}))) as LibrarySearchResponse;
  if (!response.ok) {
    throw new Error(payload.error?.trim() || "Recherche catalogue impossible.");
  }
  return {
    hits: Array.isArray(payload.hits) ? payload.hits : [],
    estimatedTotalHits: payload.estimatedTotalHits,
  };
}
