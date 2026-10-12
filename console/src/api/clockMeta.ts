import type { Clock, ClockPosition, PositionKind } from "./types";

export const KIND_LABELS: Record<PositionKind, string> = {
  jingle: "Jingle",
  son: "Programme",
  pub: "Pub",
  musique: "Titres",
};

export function kindLabel(kind: PositionKind): string {
  return KIND_LABELS[kind];
}

export type ClockCartUsage = {
  clockId: number;
  clockName: string;
  where: "motif" | "anchor" | "fallback";
  kind: PositionKind | "secours";
  index?: number;
  minute?: number;
  label: string;
};

function titlesMatch(left: string | null | undefined, right: string): boolean {
  const a = (left || "").trim().toLowerCase();
  const b = right.trim().toLowerCase();
  return Boolean(a) && a === b;
}

export function positionUsesCart(pos: ClockPosition, cart: { id: number; title: string }): boolean {
  if (pos.cart_id != null && pos.cart_id === cart.id) return true;
  return titlesMatch(pos.cart, cart.title);
}

export function clockHasCart(clock: Clock, cart: { id: number; title: string }): boolean {
  return [...clock.motif, ...clock.anchors].some((pos) => positionUsesCart(pos, cart));
}

export function clockCartUsages(clocks: Clock[], cart: { id: number; title: string }): ClockCartUsage[] {
  const usages: ClockCartUsage[] = [];
  for (const clock of clocks) {
    clock.motif.forEach((step, index) => {
      if (!positionUsesCart(step, cart)) return;
      usages.push({
        clockId: clock.id,
        clockName: clock.name,
        where: "motif",
        kind: step.kind,
        index,
        label: `${clock.name} · ${kindLabel(step.kind)} #${index + 1}`,
      });
    });
    for (const step of clock.anchors) {
      if (!positionUsesCart(step, cart)) continue;
      const minute = step.minute ?? 0;
      usages.push({
        clockId: clock.id,
        clockName: clock.name,
        where: "anchor",
        kind: step.kind,
        minute,
        label: `${clock.name} · ${kindLabel(step.kind)} :${String(minute).padStart(2, "0")}`,
      });
    }
    if (titlesMatch(clock.fallback_cart, cart.title) || clock.fallback_cart_id === cart.id) {
      usages.push({
        clockId: clock.id,
        clockName: clock.name,
        where: "fallback",
        kind: "secours",
        label: `${clock.name} · secours d’horloge`,
      });
    }
  }
  return usages;
}

export function hourUsages(usages: ClockCartUsage[]): ClockCartUsage[] {
  return usages.filter((usage) => usage.where !== "fallback");
}
