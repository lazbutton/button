import type { Clock, ClockPosition, PositionKind } from "./types";
import { apiPut } from "./client";
import { clockHasCart, positionUsesCart, withoutLibrarySteps } from "./clockMeta";

export function cartRef(
  carts: { id: number; title: string }[],
  title: string | null | undefined,
): { cart: string | null; cart_id: number | null } {
  const wanted = (title || "").trim();
  if (!wanted) return { cart: null, cart_id: null };
  const hit = carts.find((cart) => cart.title.trim().toLowerCase() === wanted.toLowerCase());
  return { cart: hit?.title ?? wanted, cart_id: hit?.id ?? null };
}

export async function saveClock(clock: Clock): Promise<Clock> {
  const payload = await apiPut<{ clock: Clock }>(`/autodj/clocks/${clock.id}.json`, {
    name: clock.name,
    version: clock.version,
    fallback_cart: clock.fallback_cart,
    fallback_cart_id: clock.fallback_cart_id ?? null,
    motif: withoutLibrarySteps(clock.motif),
    anchors: clock.anchors,
  });
  return payload.clock;
}

export function emptyMotifStep(opts?: {
  category?: string | null;
  fallback?: string | null;
  kind?: PositionKind;
  cart?: string | null;
}): ClockPosition {
  const kind = opts?.kind ?? "son";
  const usesCategory = kind === "musique";
  return {
    kind,
    when: "sequential",
    cart: usesCategory ? null : (opts?.cart ?? null),
    category: usesCategory ? (opts?.category ?? null) : null,
    fallback_cart: opts?.fallback ?? null,
  };
}

export function emptyAnchor(
  minute: number,
  opts?: { cart?: string | null; fallback?: string | null },
): ClockPosition {
  return {
    kind: "pub",
    when: "anchored",
    cart: opts?.cart ?? null,
    category: null,
    fallback_cart: opts?.fallback ?? null,
    minute,
    sync: "dure",
  };
}

export function putCartInClock(
  clock: Clock,
  cart: { id: number; title: string },
  kind: Exclude<PositionKind, "musique">,
  replaceIndex: number | null = null,
): { clock: Clock; already: boolean } {
  if (clockHasCart(clock, cart)) return { clock, already: true };
  const step = emptyMotifStep({
    kind,
    cart: cart.title,
    fallback: clock.fallback_cart || null,
  });
  step.cart_id = cart.id;
  if (replaceIndex != null && clock.motif[replaceIndex]) {
    const motif = clock.motif.slice();
    motif[replaceIndex] = {
      ...motif[replaceIndex],
      kind,
      when: "sequential",
      cart: cart.title,
      cart_id: cart.id,
      category: null,
    };
    return { clock: { ...clock, motif }, already: false };
  }
  return { clock: { ...clock, motif: [...clock.motif, step] }, already: false };
}

export function removeCartFromClock(
  clock: Clock,
  cart: { id: number; title: string },
): { clock: Clock; removed: boolean } {
  const motif = clock.motif.filter((pos) => !positionUsesCart(pos, cart));
  const anchors = clock.anchors.filter((pos) => !positionUsesCart(pos, cart));
  const removed = motif.length !== clock.motif.length || anchors.length !== clock.anchors.length;
  if (!removed) return { clock, removed: false };
  return { clock: { ...clock, motif, anchors }, removed: true };
}

export async function removeCartFromClocks(
  clocks: Clock[],
  cart: { id: number; title: string },
): Promise<{ count: number; names: string[] }> {
  const names: string[] = [];
  for (const clock of clocks) {
    const next = removeCartFromClock(clock, cart);
    if (!next.removed) continue;
    await saveClock(next.clock);
    names.push(clock.name);
  }
  return { count: names.length, names };
}

export function setClockPositionCart(
  clock: Clock,
  cart: { id: number; title: string },
  match: {
    positionId?: number | null;
    motifIndex?: number | null;
    kind?: string;
    previousCart?: string | null;
  },
): Clock {
  const patch = (pos: ClockPosition, index: number, where: "motif" | "anchor") => {
    if (match.positionId != null && pos.id === match.positionId) return true;
    if (where === "motif" && match.motifIndex != null && index === match.motifIndex) return true;
    if (match.positionId != null || match.motifIndex != null) return false;
    if (match.kind && pos.kind !== match.kind) return false;
    const previous = (match.previousCart || "").trim().toLowerCase();
    if (previous && (pos.cart || "").trim().toLowerCase() === previous) return true;
    return !pos.cart && pos.kind === match.kind;
  };
  const apply = (pos: ClockPosition): ClockPosition => ({
    ...pos,
    cart: cart.title,
    cart_id: cart.id,
    category: pos.kind === "musique" ? pos.category : null,
  });
  return {
    ...clock,
    motif: clock.motif.map((pos, index) =>
      patch(pos, index, "motif") ? apply(pos) : pos,
    ),
    anchors: clock.anchors.map((pos, index) =>
      patch(pos, index, "anchor") ? apply(pos) : pos,
    ),
  };
}

export function mergeClockPosition(
  current: ClockPosition | undefined,
  next: ClockPosition,
): ClockPosition {
  if (!current) return next;
  return {
    ...current,
    ...next,
    id: next.id ?? current.id,
  };
}

export function clockPositionsEqual(left: Clock, right: Clock): boolean {
  return (
    JSON.stringify({
      motif: left.motif,
      anchors: left.anchors,
      fallback: left.fallback_cart,
    }) ===
    JSON.stringify({
      motif: right.motif,
      anchors: right.anchors,
      fallback: right.fallback_cart,
    })
  );
}
