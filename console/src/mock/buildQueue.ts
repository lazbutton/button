import { parisParts } from "../lib/parisClock";
import {
  CATALOG,
  CLOCKS,
  itemsByCart,
  itemsByCategory,
  itemsByKind,
  type CatalogItem,
  type ClockDef,
} from "./catalog";

export type QueueItem = {
  uid: string;
  item: CatalogItem;
  role: "seq" | "anchor";
  anchor?: ":20" | ":40";
};

export type ClockAnchorHit = {
  remainingSec: number;
  label: ":20" | ":40";
  minute: 20 | 40;
};

const JOURNEE_START = 10 * 60;
const JOURNEE_END = 18 * 60;

let uidSeq = 0;

function nextUid(): string {
  uidSeq += 1;
  return `q${uidSeq}`;
}

function pick(list: CatalogItem[], index: number): CatalogItem {
  return list[index % list.length];
}

function labelForMinute(minute: 20 | 40): ":20" | ":40" {
  return minute === 20 ? ":20" : ":40";
}

/** Hard anchors of this clock that fall in the next ``horizonSec``, in daypart 10:00–18:00. */
export function clockAnchorsInWindow(
  clock: ClockDef,
  now: Date,
  horizonSec = 34 * 60,
): ClockAnchorHit[] {
  if (!clock.anchors.length) return [];
  const { hour, minute, second } = parisParts(now);
  const nowSec = hour * 3600 + minute * 60 + second;
  const hits: ClockAnchorHit[] = [];
  for (let addH = 0; addH <= 2; addH += 1) {
    const h = hour + addH;
    const civilHour = ((h % 24) + 24) % 24;
    const dayAdd = Math.floor(h / 24) * 86400;
    for (const anchor of clock.anchors) {
      const abs = dayAdd + civilHour * 3600 + anchor.minute * 60;
      const remaining = abs - nowSec;
      if (remaining <= 0 || remaining > horizonSec) continue;
      const minuteOfDay = civilHour * 60 + anchor.minute;
      if (minuteOfDay < JOURNEE_START || minuteOfDay >= JOURNEE_END) continue;
      hits.push({
        remainingSec: remaining,
        label: labelForMinute(anchor.minute),
        minute: anchor.minute,
      });
    }
  }
  hits.sort((a, b) => a.remainingSec - b.remainingSec);
  return hits;
}

export function nextClockAnchor(clock: ClockDef, now: Date): ClockAnchorHit | null {
  return clockAnchorsInWindow(clock, now, 60 * 60)[0] ?? null;
}

export function buildQueue(
  clock: ClockDef,
  now: Date,
  musicCursor = 0,
  jingleCursor = 0,
  pubCursor = 0,
): QueueItem[] {
  const musics = itemsByCategory("Rotation");
  const archives = itemsByCategory("Archives");
  const jingles = itemsByCart("Jingles");
  const pubs = itemsByCart("Pubs");
  const items: QueueItem[] = [];
  let elapsed = 0;
  const target = 34 * 60;
  const pending = clockAnchorsInWindow(clock, now, target);
  let pendingI = 0;
  let m = musicCursor;
  let j = jingleCursor;
  let p = pubCursor;
  let motifI = 0;

  const peekStep = (step: ClockDef["motif"][number]): CatalogItem => {
    if (step.kind === "jingle") return pick(jingles, j);
    if (step.kind === "pub") return pick(pubs, p);
    if (step.kind === "son") return pick(itemsByKind("son"), m);
    if (step.category === "Archives") return pick(archives, m);
    return pick(musics, m);
  };

  const consumeStep = (step: ClockDef["motif"][number]): CatalogItem => {
    if (step.kind === "jingle") return pick(jingles, j++);
    if (step.kind === "pub") return pick(pubs, p++);
    if (step.kind === "son") return pick(itemsByKind("son"), m++);
    if (step.category === "Archives") return pick(archives, m++);
    return pick(musics, m++);
  };

  while (elapsed < target || items.length < 10) {
    const nextA = pending[pendingI];
    const step = clock.motif[motifI % clock.motif.length];
    const seqItem = peekStep(step);
    if (nextA && elapsed + seqItem.durationSec > nextA.remainingSec) {
      const pub = pick(pubs, p++);
      items.push({
        uid: nextUid(),
        item: pub,
        role: "anchor",
        anchor: nextA.label,
      });
      elapsed = Math.max(elapsed, nextA.remainingSec) + pub.durationSec;
      pendingI += 1;
      if (items.length > 40) break;
      continue;
    }
    motifI += 1;
    items.push({ uid: nextUid(), item: consumeStep(step), role: "seq" });
    elapsed += seqItem.durationSec;
    if (items.length > 40) break;
  }

  return items;
}

export function buildPastQueue(clock: ClockDef, count = 8): QueueItem[] {
  const musics = itemsByCategory("Rotation");
  const archives = itemsByCategory("Archives");
  const jingles = itemsByCart("Jingles");
  const pubs = itemsByCart("Pubs");
  let m = musics.length - 1;
  let j = jingles.length - 1;
  let p = pubs.length - 1;
  const items: QueueItem[] = [];

  const resolveStep = (step: ClockDef["motif"][number]): CatalogItem => {
    if (step.kind === "jingle") {
      const item = pick(jingles, Math.max(0, j));
      j -= 1;
      return item;
    }
    if (step.kind === "pub") {
      const item = pick(pubs, Math.max(0, p));
      p -= 1;
      return item;
    }
    if (step.kind === "son") return pick(itemsByKind("son"), 0);
    if (step.category === "Archives") {
      const item = pick(archives, Math.max(0, m));
      m -= 1;
      return item;
    }
    const item = pick(musics, Math.max(0, m));
    m -= 1;
    return item;
  };

  for (let i = 0; i < count; i += 1) {
    const step = clock.motif[i % clock.motif.length];
    items.push({ uid: nextUid(), item: resolveStep(step), role: "seq" });
  }
  return items;
}

export function defaultClock(now: Date): ClockDef {
  const { hour } = parisParts(now);
  return hour >= 10 && hour < 18 ? CLOCKS[0] : CLOCKS[1];
}

export function findItem(id: string): CatalogItem | undefined {
  return CATALOG.find((i) => i.id === id);
}
