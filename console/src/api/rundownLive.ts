import { displayNow } from "../lib/nowPlaying.ts";
import type { LiveSnapshot, RundownItem } from "./types";

const PAST_CODES = new Set(["played", "skipped", "replaced"]);

const LABEL_TO_CODE: Record<string, string> = {
  prévu: "planned",
  réservé: "reserved",
  "en attente de push": "pending_push",
  envoyé: "sent",
  accepté: "accepted",
  "en file": "in_queue",
  "à l'antenne": "on_air",
  joué: "played",
  sauté: "skipped",
  remplacé: "replaced",
  secours: "rescue",
  manquant: "failed",
  échec: "failed",
};

export function itemStartMs(item: RundownItem): number {
  const start = Date.parse(item.at);
  return Number.isFinite(start) ? start : Number.NaN;
}

export function itemEndMs(item: RundownItem): number {
  const start = itemStartMs(item);
  if (!Number.isFinite(start)) return Number.POSITIVE_INFINITY;
  const duration = Number(item.duration);
  const sec = Number.isFinite(duration) && duration > 0 ? duration : 0;
  if (sec <= 0) return start + 8000;
  return start + sec * 1000;
}

export function isMissingClockCart(item: RundownItem): boolean {
  if (item.kind === "musique") return false;
  return item.status === "manquant";
}

export function itemStatusCode(item: RundownItem): string {
  if (item.status_code) return item.status_code;
  const mapped = LABEL_TO_CODE[item.status];
  if (mapped) return mapped;
  if (item.fallback_used) return "rescue";
  return "planned";
}

export function visibleRundownItems(
  items: RundownItem[],
  wall: Date,
): RundownItem[] {
  const t = wall.getTime();
  return items.filter((item) => {
    const code = itemStatusCode(item);
    if (PAST_CODES.has(code)) return false;
    return itemEndMs(item) > t;
  });
}

export function itemRemainingSec(item: RundownItem, wall: Date): number {
  return Math.max(0, Math.round((itemEndMs(item) - wall.getTime()) / 1000));
}

const GENERIC_LIVE_NAMES = new Set([
  "jingles",
  "pubs",
  "pub",
  "rotation",
  "programme",
  "prog",
  "musique manquante",
  "cart",
  "carts",
]);

function liveLabelIsGeneric(value: string | undefined | null): boolean {
  const text = (value || "").trim().toLowerCase();
  if (!text) return true;
  return GENERIC_LIVE_NAMES.has(text);
}

export function itemNamedLikeLive(item: RundownItem, live: LiveSnapshot | null): boolean {
  if (!live || live.status === "offline") return false;
  const title = live.title?.trim();
  const artist = live.artist?.trim();
  if (
    title &&
    !liveLabelIsGeneric(title) &&
    (item.title?.trim() === title || item.resource.includes(title))
  ) {
    return true;
  }
  if (
    artist &&
    !liveLabelIsGeneric(artist) &&
    (item.resource.includes(artist) || item.cart === artist || item.artist?.trim() === artist)
  ) {
    return true;
  }
  return false;
}

export function itemMatchesLive(
  item: RundownItem,
  live: LiveSnapshot | null,
  wall?: Date,
): boolean {
  if (!itemNamedLikeLive(item, live)) return false;
  if (!wall) return true;
  const t = wall.getTime();
  const start = itemStartMs(item);
  const end = itemEndMs(item);
  if (!Number.isFinite(start)) return true;
  return start - 1500 <= t && t < end + 1500;
}

export function liveQueue(
  live: LiveSnapshot | null,
): "carts" | "jingles" | "autodj" | null {
  if (!live || live.status === "offline") return null;
  const source = (live.source || "").toLowerCase();
  if (source.includes("jingle")) return "jingles";
  if (source.includes("cart")) return "carts";
  if (live.kind === "jingle") return "jingles";
  if (live.kind === "son" || live.kind === "pub") return "carts";
  if (source.includes("autodj")) return "autodj";
  return null;
}

export function liveCartRundownItem(
  live: LiveSnapshot | null,
  wall: Date = new Date(),
): RundownItem | null {
  const queue = liveQueue(live);
  if (!live || (queue !== "carts" && queue !== "jingles")) return null;
  if (liveLabelIsGeneric(live.title) && liveLabelIsGeneric(live.artist)) return null;
  const cart = live.artist?.trim() || "";
  const title = live.title?.trim() || "";
  const resource =
    cart && title && cart !== title ? `${cart} — ${title}` : title || cart || "Cart";
  const elapsed = Number(live.elapsed) || 0;
  const remaining = Number(live.remaining) || 0;
  const started = new Date(wall.getTime() - elapsed * 1000);
  return {
    at: Number.isFinite(started.getTime()) ? started.toISOString() : wall.toISOString(),
    kind: queue === "jingles" ? "jingle" : live.kind || "son",
    when: "live",
    resource,
    queue,
    status: "à l'antenne",
    status_code: "on_air",
    clock: "",
    daypart: "",
    cart: cart || undefined,
    duration: Math.max(1, elapsed + remaining),
  };
}

export function liveHarborRundownItem(
  live: LiveSnapshot | null,
  wall: Date = new Date(),
): RundownItem | null {
  if (!live || live.status === "offline" || !isHarborSource(live.source)) return null;
  const title = live.title?.trim() || live.emission?.title?.trim() || "Direct";
  const artist = live.artist?.trim() || live.emission?.artist?.trim() || "";
  const elapsed = Number(live.elapsed) || 0;
  const remaining = Number(live.remaining) || 0;
  const started = new Date(wall.getTime() - elapsed * 1000);
  return {
    at: Number.isFinite(started.getTime()) ? started.toISOString() : wall.toISOString(),
    kind: "son",
    when: "live",
    resource: artist && artist !== title ? `${artist} — ${title}` : title,
    queue: "stream",
    status: "à l'antenne",
    status_code: "on_air",
    clock: "",
    daypart: "",
    origin: "live",
    title,
    artist: artist || undefined,
    duration: Math.max(1, elapsed + remaining),
  };
}

export type PartitionedRundown = {
  past: RundownItem[];
  onAir: RundownItem | null;
  upcoming: RundownItem[];
};

export const CONDUCTEUR_JSON = "/autodj/conducteur.json?horizon=360";
export const DESK_FILE_AHEAD = 10;

export function isDeskPin(item: RundownItem): boolean {
  if (item.origin !== "desk" || !item.id) return false;
  return !item.id.startsWith("clock|");
}

export function queueItemKey(item: RundownItem, index = 0): string {
  return item.id || `${item.at}:${item.path || item.resource}:${index}`;
}

export function queueItemLocked(item: RundownItem, onAirId?: string): boolean {
  if (item.id && onAirId && item.id === onAirId) return true;
  if (itemStatusCode(item) === "on_air") return true;
  return item.when === "anchored";
}

export function itemUntilAirSec(item: RundownItem, wall: Date): number {
  const start = itemStartMs(item);
  if (!Number.isFinite(start)) return 0;
  return Math.max(0, Math.round((start - wall.getTime()) / 1000));
}

export function partitionRundown(
  items: RundownItem[],
  wall: Date,
  live: LiveSnapshot | null,
): PartitionedRundown {
  const t = wall.getTime();
  const liveIndex = items.findIndex((item) => {
    if (itemEndMs(item) <= t) return false;
    if (PAST_CODES.has(itemStatusCode(item))) return false;
    return itemStatusCode(item) === "on_air" || itemNamedLikeLive(item, live);
  });
  const coveringIndex = items.findIndex((item) => {
    const start = itemStartMs(item);
    const end = itemEndMs(item);
    if (!Number.isFinite(start)) return false;
    return start <= t && t < end;
  });
  const harbor = Boolean(live && live.status !== "offline" && isHarborSource(live.source));
  const liveCart = liveCartRundownItem(live, wall);
  const inRundown = Boolean(live && items.some((item) => itemNamedLikeLive(item, live)));
  const firstLive = items.findIndex((item) => {
    const code = itemStatusCode(item);
    if (PAST_CODES.has(code)) return false;
    return itemEndMs(item) > t;
  });
  const padInsert =
    Boolean(liveCart) &&
    !inRundown &&
    (isHarborSource(live?.source) || liveQueue(live) === "carts" || liveQueue(live) === "jingles");
  const onAirIndex = harbor || padInsert
    ? -1
    : liveIndex >= 0
      ? liveIndex
      : coveringIndex >= 0
        ? coveringIndex
        : firstLive;

  const past: RundownItem[] = [];
  const upcoming: RundownItem[] = [];
  let onAir: RundownItem | null = null;

  items.forEach((item, index) => {
    if (index === onAirIndex) {
      onAir = item;
      return;
    }
    const code = itemStatusCode(item);
    const ended = PAST_CODES.has(code) || itemEndMs(item) <= wall.getTime();
    if (onAirIndex >= 0 && index < onAirIndex) {
      past.push(item);
      return;
    }
    if (ended) {
      past.push(item);
      return;
    }
    upcoming.push(item);
  });

  if (!onAir && liveCart) {
    onAir = liveCart;
  }
  if (!onAir && harbor) {
    onAir = liveHarborRundownItem(live, wall);
  }

  return { past: past.slice(-8), onAir, upcoming };
}

export function isHarborSource(source: string | undefined | null): boolean {
  const text = (source || "").trim().toLowerCase();
  if (!text) return false;
  return text.includes("stream") || text.includes("harbor");
}

export function rundownFileHref(item: RundownItem | null | undefined): string | null {
  if (!item) return null;
  const cartId = Number(item.cart_id);
  const soundId = Number(item.sound_id);
  if (Number.isFinite(cartId) && cartId > 0 && Number.isFinite(soundId) && soundId > 0) {
    return `/carts/${cartId}/sounds/${soundId}`;
  }
  const beetsId = Number(item.beets_id);
  if (Number.isFinite(beetsId) && beetsId > 0) return `/autodj/beets/${beetsId}`;
  return null;
}

export function rundownItemKey(item: RundownItem | null | undefined): string {
  if (!item) return "";
  if (item.id) return item.id;
  const href = rundownFileHref(item) || item.resource || "";
  return `${item.at}|${href}`;
}

export type AntennaFile = {
  key: string;
  cartId: number;
  soundId: number;
  beetsId: number;
  elapsed: number;
  duration: number;
  title: string;
  artist: string;
};

/** Fichier réellement à l’antenne, d’après le battement Liquidsoap. */
export function antennaFile(live: LiveSnapshot | null): AntennaFile | null {
  if (!live || live.status === "offline" || isHarborSource(live.source)) return null;
  const uri = live.initial_uri || "";
  const soundFromUri = uri.match(/radiotomate_sound_id="(\d+)"/);
  const soundId = Number(live.radiotomate_sound_id || soundFromUri?.[1] || 0);
  const pathMatch = uri.match(/:(\/media\/\S+)$/) || uri.match(/(\/media\/\S+)$/);
  const path = pathMatch?.[1] || "";
  const cartMatch = path.match(/\/50-carts\/(\d+)\//);
  const cartId = cartMatch ? Number(cartMatch[1]) : 0;
  const beetsFromUri = uri.match(/beets_id="(\d+)"/);
  const beetsId = beetsFromUri ? Number(beetsFromUri[1]) : 0;
  if (!(soundId > 0 && cartId > 0) && !(beetsId > 0)) return null;
  const elapsed = Number(live.elapsed);
  const elapsedSec = Number.isFinite(elapsed) && elapsed >= 0 ? elapsed : 0;
  const remaining = Number(live.remaining);
  const remainingSec = Number.isFinite(remaining) && remaining > 0 ? remaining : 0;
  const duration = Math.max(elapsedSec + remainingSec, Number(live.duration) || 0, 1);
  return {
    key: `${soundId}:${cartId}:${beetsId}:${live.on_air || ""}:${live.title || ""}`,
    cartId,
    soundId,
    beetsId,
    elapsed: elapsedSec,
    duration,
    title: live.title || path.split("/").pop() || "Antenne",
    artist: live.artist || "",
  };
}

export function antennaNextItem(live: LiveSnapshot | null, wall: Date): RundownItem | null {
  const cue = live?.next_autodj || live?.next_jingle || live?.next_cart;
  if (!cue?.initial_uri) return null;
  const file = antennaFile({
    status: "playing",
    source: "autodj",
    title: cue.title,
    artist: cue.artist,
    initial_uri: cue.initial_uri,
    elapsed: 0,
    on_air: `next:${cue.rid}`,
  });
  if (!file) return null;
  const remaining = Number(live?.remaining);
  const wait = Number.isFinite(remaining) && remaining > 0 ? remaining : 0;
  return antennaRundownItem(file, wall.getTime() + wait * 1000);
}

/** Item calé sur la position antenne, pas sur l’heure prévue du conducteur. */
export function antennaRundownItem(
  file: AntennaFile,
  startedAtMs: number,
): RundownItem {
  return {
    id: `antenna:${file.key}`,
    at: new Date(startedAtMs).toISOString(),
    duration: file.duration,
    kind: "son",
    when: "live",
    resource: file.title,
    queue: "autodj",
    status: "à l'antenne",
    status_code: "on_air",
    clock: "",
    daypart: "",
    title: file.title,
    artist: file.artist,
    cart_id: file.cartId || null,
    sound_id: file.soundId || null,
    beets_id: file.beetsId || null,
  };
}

/** Écart mural signé : négatif = l’item n’a pas encore commencé. */
export function clockElapsedSec(item: RundownItem, wall: Date): number {
  const start = itemStartMs(item);
  if (!Number.isFinite(start)) return 0;
  return (wall.getTime() - start) / 1000;
}

function fileItemsCovering(items: RundownItem[], wall: Date): RundownItem[] {
  const t = wall.getTime();
  return items.filter((item) => {
    if (!rundownFileHref(item)) return false;
    const start = itemStartMs(item);
    const end = itemEndMs(item);
    return Number.isFinite(start) && start <= t && t < end;
  });
}

/** Parmi les fichiers qui couvrent maintenant, celui qui a démarré le plus tard (ancre qui coupe). */
export function clockCoveringItem(items: RundownItem[], wall: Date): RundownItem | null {
  const covering = fileItemsCovering(items, wall);
  if (!covering.length) return null;
  covering.sort((a, b) => {
    const startDelta = itemStartMs(b) - itemStartMs(a);
    if (startDelta) return startDelta;
    if (a.when === "anchored" && b.when !== "anchored") return -1;
    if (b.when === "anchored" && a.when !== "anchored") return 1;
    return 0;
  });
  return covering[0] ?? null;
}

export function clockPlayableItem(items: RundownItem[], wall: Date): RundownItem | null {
  const covering = clockCoveringItem(items, wall);
  if (covering) return covering;
  const t = wall.getTime();
  return (
    items
      .filter((item) => {
        if (!rundownFileHref(item)) return false;
        const start = itemStartMs(item);
        return Number.isFinite(start) && start > t;
      })
      .sort((a, b) => itemStartMs(a) - itemStartMs(b))[0] ?? null
  );
}

export function clockNextFileItem(
  items: RundownItem[],
  current: RundownItem,
): RundownItem | null {
  const curStart = itemStartMs(current);
  const curKey = rundownItemKey(current);
  if (!Number.isFinite(curStart)) return null;
  return (
    items
      .filter((item) => {
        if (rundownItemKey(item) === curKey) return false;
        if (!rundownFileHref(item)) return false;
        const start = itemStartMs(item);
        return Number.isFinite(start) && start > curStart;
      })
      .sort((a, b) => itemStartMs(a) - itemStartMs(b))[0] ?? null
  );
}

export function playableRundownItem(
  items: RundownItem[],
  live: LiveSnapshot | null,
  wall: Date,
): RundownItem | null {
  const t = wall.getTime();
  const covering = items.find((item) => {
    if (!rundownFileHref(item)) return false;
    const start = itemStartMs(item);
    const end = itemEndMs(item);
    return Number.isFinite(start) && start <= t && t < end;
  });
  if (covering) return covering;
  const { onAir, upcoming } = partitionRundown(items, wall, live);
  if (onAir && rundownFileHref(onAir)) {
    const start = itemStartMs(onAir);
    if (!Number.isFinite(start) || start - t <= 400) return onAir;
  }
  const liveFile = items.find(
    (item) =>
      Boolean(rundownFileHref(item)) &&
      itemMatchesLive(item, live, wall) &&
      itemEndMs(item) > t,
  );
  if (liveFile) return liveFile;
  return upcoming.find((item) => Boolean(rundownFileHref(item))) ?? null;
}

export function liveTitleHits(item: RundownItem, live: LiveSnapshot | null): boolean {
  const title = live?.title?.trim();
  if (!title || liveLabelIsGeneric(title)) return false;
  return item.resource.includes(title);
}

export function itemElapsedSec(
  item: RundownItem,
  live: LiveSnapshot | null,
  wall: Date,
): number {
  if (
    liveTitleHits(item, live) &&
    itemMatchesLive(item, live, wall) &&
    typeof live?.elapsed === "number" &&
    live.elapsed >= 0
  ) {
    const duration = Number(item.duration);
    if (!Number.isFinite(duration) || duration <= 0 || live.elapsed <= duration + 2) {
      return live.elapsed;
    }
  }
  const start = itemStartMs(item);
  if (!Number.isFinite(start)) return 0;
  return Math.max(0, (wall.getTime() - start) / 1000);
}

export function rundownCopy(item: RundownItem): { title: string; artist?: string } {
  const parsed = displayNow({
    title: item.title || item.resource,
    artist: item.artist || "",
  });
  const title = parsed.title.trim();
  const artist = parsed.artist.trim();
  if (!title && !artist) return { title: "—" };
  if (!title) return { title: artist };
  return artist ? { title, artist } : { title };
}

export function nextAnchoredItem(
  items: RundownItem[],
  wall: Date,
): RundownItem | null {
  return (
    items.find((item) => {
      if (item.when !== "anchored") return false;
      if (PAST_CODES.has(itemStatusCode(item))) return false;
      const start = itemStartMs(item);
      return !Number.isFinite(start) || start >= wall.getTime() - 1000;
    }) ?? null
  );
}
