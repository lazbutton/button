import { displayNow } from "../lib/nowPlaying";
import type { CatalogItem, Kind } from "../mock/catalog";
import { harborIsLive } from "./emissionMeta";
import { itemNamedLikeLive, liveQueue, rundownCopy } from "./rundownLive";
import type { Cue, LiveSnapshot, RundownItem } from "./types";

export function kindFromSource(source: string | undefined, kind?: string): Kind {
  if (kind === "musique" || kind === "jingle" || kind === "son" || kind === "pub") {
    return kind;
  }
  const raw = (source || "").toLowerCase();
  if (/live|harbor|stream/.test(raw)) return "son";
  if (source?.includes("jingle")) return "jingle";
  if (source?.includes("cart")) return "son";
  if (source?.includes("autodj")) return "musique";
  return "son";
}

export function catalogFromRundown(
  item: RundownItem,
  liveItem?: CatalogItem,
): CatalogItem {
  const copy = rundownCopy(item);
  const kind = item.kind;
  return {
    id: item.id || "on-air",
    kind:
      kind === "musique" || kind === "jingle" || kind === "son" || kind === "pub"
        ? kind
        : liveItem?.kind ?? "son",
    title: copy.title,
    artist: copy.artist,
    cart: item.cart,
    durationSec: item.duration || liveItem?.durationSec || 0,
  };
}

export function liveToItem(live: LiveSnapshot | null): CatalogItem | undefined {
  if (!live || live.status === "offline") return undefined;
  const harbor = harborIsLive(live);
  const rawArtist = live.artist?.trim() || "";
  const labels = displayNow({
    title: live.title,
    artist: live.artist,
    album: live.album,
  });
  const title = labels.title.trim() || (harbor ? "Direct" : "");
  const artist = labels.artist.trim();
  if (!title && !artist) return undefined;
  const remaining = Math.max(0, live.remaining ?? 0);
  const elapsed = Math.max(0, live.elapsed ?? 0);
  const queue = liveQueue(live);
  const kind =
    queue === "jingles"
      ? "jingle"
      : queue === "carts"
        ? live.kind === "pub"
          ? "pub"
          : "son"
        : queue === "autodj"
          ? "musique"
          : kindFromSource(live.source, live.kind);
  return {
    id: "live-now",
    kind,
    title: title || "—",
    artist: artist || undefined,
    cart: queue === "carts" || queue === "jingles" ? rawArtist || undefined : undefined,
    durationSec: Math.max(1, Math.round(elapsed + remaining)),
  };
}

export function cueLabel(cue: Cue | null | undefined): string {
  const labels = cueLabels(cue);
  if (!labels.title && !labels.artist) return "—";
  if (labels.artist && labels.title) return `${labels.artist} — ${labels.title}`;
  return labels.title || labels.artist;
}

export function cueLabels(cue: Cue | null | undefined): { title: string; artist: string } {
  if (!cue) return { title: "", artist: "" };
  const parsed = displayNow({ title: cue.title, artist: cue.artist });
  return { title: parsed.title.trim(), artist: parsed.artist.trim() };
}

export function glanceNowItem(
  onAir: RundownItem | null,
  live: LiveSnapshot | null,
): CatalogItem | undefined {
  if (harborIsLive(live)) return liveToItem(live);
  const liveItem = liveToItem(live);
  if (onAir && itemNamedLikeLive(onAir, live) && liveItem) {
    return {
      ...catalogFromRundown(onAir, liveItem),
      title: liveItem.title,
      artist: liveItem.artist,
      kind: liveItem.kind,
      durationSec: liveItem.durationSec || catalogFromRundown(onAir).durationSec,
    };
  }
  if (onAir) return catalogFromRundown(onAir, liveItem);
  return liveItem;
}
