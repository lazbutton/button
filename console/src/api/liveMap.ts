import { identCart } from "./cartFlags";
import { displayNow } from "../lib/nowPlaying";
import type { CatalogItem, Kind } from "../mock/catalog";
import { harborIsLive } from "./emissionMeta";
import { itemNamedLikeLive, liveQueue, rundownCopy } from "./rundownLive";
import type { Cart, Cue, LiveSnapshot, RundownItem } from "./types";

export type EnginePad = {
  id: string;
  kind: "son" | "jingle" | "pub";
  title: string;
  durationSec: number;
  cartId: number;
  soundId: number;
  rank?: number;
  path?: string;
};

export const PAD_N = 6;
export const PAD_DRAG_MIME = "application/x-button-pad";

export type PadSlot = {
  slot: number;
  kind: "jingle" | "pub";
  cartId: number | null;
  pad: EnginePad | null;
};

function padFromSound(cart: Cart, sound: Cart["sounds"][number], kind: EnginePad["kind"]): EnginePad {
  return {
    id: `c${cart.id}-s${sound.id}`,
    kind,
    title: sound.title,
    durationSec: sound.duration,
    cartId: cart.id,
    soundId: sound.id,
    rank: sound.rank,
    path: sound.path,
  };
}

function soundsToPads(cart: Cart, kind: EnginePad["kind"]): EnginePad[] {
  return cart.sounds.slice(0, PAD_N).map((sound) => padFromSound(cart, sound, kind));
}

function slotsForCart(cart: Cart | undefined, kind: "jingle" | "pub"): PadSlot[] {
  const sounds = [...(cart?.sounds ?? [])].sort((left, right) => left.rank - right.rank);
  return Array.from({ length: PAD_N }, (_, index) => {
    const sound = sounds[index];
    return {
      slot: index + 1,
      kind,
      cartId: cart?.id ?? null,
      pad: sound && cart ? padFromSound(cart, sound, kind) : null,
    };
  });
}

export function padSlotsFromCarts(carts: Cart[]): { jingle: PadSlot[]; pub: PadSlot[] } {
  const jingles = identCart(carts);
  const pubs = carts.find((cart) => cart.title === "Pubs");
  return {
    jingle: slotsForCart(jingles, "jingle"),
    pub: slotsForCart(pubs, "pub"),
  };
}

export function padBanksFromCarts(carts: Cart[]): {
  son: EnginePad[];
  jingle: EnginePad[];
  pub: EnginePad[];
} {
  const jingles = identCart(carts);
  const pubs = carts.find((cart) => cart.title === "Pubs");
  const others = carts.filter((cart) => cart.id !== jingles?.id && cart.id !== pubs?.id);
  const son: EnginePad[] = [];
  for (const cart of others) {
    for (const sound of cart.sounds) {
      if (son.length >= PAD_N) break;
      son.push({
        id: `c${cart.id}-s${sound.id}`,
        kind: "son",
        title: sound.title,
        durationSec: sound.duration,
        cartId: cart.id,
        soundId: sound.id,
      });
    }
  }
  return {
    son,
    jingle: jingles ? soundsToPads(jingles, "jingle") : [],
    pub: pubs ? soundsToPads(pubs, "pub") : [],
  };
}

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

export function onAirPadId(
  live: LiveSnapshot | null,
  banks: { son: EnginePad[]; jingle: EnginePad[]; pub: EnginePad[] },
): string | undefined {
  const title = live?.title?.trim();
  if (!title) return undefined;
  for (const bank of [banks.jingle, banks.son, banks.pub]) {
    const hit = bank.find((pad) => pad.title === title);
    if (hit) return hit.id;
  }
  return undefined;
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

export function padCaption(raw: string): { title: string; artist: string } {
  const parsed = displayNow({ title: raw, artist: "" });
  return {
    title: parsed.title.trim() || raw.trim() || "—",
    artist: parsed.artist.trim(),
  };
}

export function liveSourceLabel(live: LiveSnapshot | null): { label: string; color: "gray" | "green" | "red" } {
  if (!live || live.status === "offline") return { label: "Arrêt", color: "gray" };
  const raw = (live.source || "").trim().toLowerCase();
  if (/live|harbor|stream/.test(raw)) return { label: "Direct", color: "red" };
  if (raw.includes("jingle")) return { label: "Jingles", color: "green" };
  if (raw.includes("cart")) return { label: "Carts", color: "green" };
  if (raw.includes("relay") || raw.includes("relais")) return { label: "Relais", color: "green" };
  return { label: "Auto-DJ", color: "green" };
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
