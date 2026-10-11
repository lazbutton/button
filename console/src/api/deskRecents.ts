import type { LibraryHit } from "./library";

const KEY = "app-desk-recents";
const MAX = 8;

function asHit(value: unknown): LibraryHit | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Partial<LibraryHit>;
  if (typeof row.path !== "string" || !row.path.trim()) return null;
  return {
    id: typeof row.id === "string" ? row.id : row.path,
    path: row.path,
    filename: typeof row.filename === "string" ? row.filename : undefined,
    title: typeof row.title === "string" ? row.title : row.path,
    artist: typeof row.artist === "string" ? row.artist : "",
    kind: typeof row.kind === "string" ? row.kind : "son",
    grouping: typeof row.grouping === "string" ? row.grouping : undefined,
    folder: typeof row.folder === "string" ? row.folder : undefined,
    duration: typeof row.duration === "number" ? row.duration : 0,
  };
}

export function readDeskRecents(): LibraryHit[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(KEY) || "[]") as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.map(asHit).filter((hit): hit is LibraryHit => hit != null).slice(0, MAX);
  } catch {
    return [];
  }
}

export function pushDeskRecent(hit: LibraryHit): LibraryHit[] {
  const next = [hit, ...readDeskRecents().filter((row) => row.path !== hit.path)].slice(0, MAX);
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* proto */
  }
  return next;
}
