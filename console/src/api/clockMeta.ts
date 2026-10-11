import { parisParts, parisWeekdayMon0 } from "../lib/parisClock";
import { daypartRanges, rangeAtMinute } from "./clockCss";
import type {
  Cart,
  Category,
  Clock,
  ClockPosition,
  PositionKind,
  Slot,
} from "./types";

export const KIND_LABELS: Record<PositionKind, string> = {
  jingle: "Jingle",
  son: "Programme",
  pub: "Pub",
  musique: "Bibliothèque",
};

export const KIND_ORDER: PositionKind[] = ["jingle", "son", "pub"];

export const KIND_HELP: Record<PositionKind, string> = {
  jingle: "Cart Jingles : coupe souvent le titre en cours.",
  son: "Cart de titres (Prog par défaut), file Auto-DJ.",
  pub: "Cart pubs, souvent calé à une minute pile.",
  musique: "Catégorie Beets — optionnel, ce n’est pas un cart.",
};

export function kindLabel(kind: PositionKind): string {
  return KIND_LABELS[kind];
}

export function sourceLabel(step: ClockPosition): string {
  if (step.kind === "musique") {
    const name = (step.category || "").trim();
    return name ? `Sélection ${name}` : "Sélection à choisir";
  }
  const name = (step.cart || "").trim();
  return name ? `Cart ${name}` : "Cart à choisir";
}

export function stepHeadline(step: ClockPosition): string {
  return `${kindLabel(step.kind)} · ${sourceLabel(step)}`;
}

export type FillBand = { start: number; end: number };

export function fillBands(anchors: ClockPosition[]): FillBand[] {
  const minutes = [
    ...new Set(
      anchors
        .map((row) => row.minute)
        .filter((minute): minute is number => minute != null && minute >= 0 && minute <= 59),
    ),
  ].sort((a, b) => a - b);
  if (!minutes.length) return [{ start: 0, end: 60 }];
  const bands: FillBand[] = [];
  let cursor = 0;
  for (const minute of minutes) {
    if (minute > cursor) bands.push({ start: cursor, end: minute });
    cursor = minute;
  }
  if (cursor < 60) bands.push({ start: cursor, end: 60 });
  return bands.filter((band) => band.end > band.start);
}

const DAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"] as const;

export function slotUsages(slots: Slot[], clockId: number, clockName?: string): string[] {
  return slots
    .filter((slot) => slot.clock_id === clockId || (clockName != null && slot.clock === clockName))
    .sort((a, b) => a.day_of_week - b.day_of_week || a.minute - b.minute)
    .map((slot) => {
      const hour = Math.floor(slot.minute / 60);
      return `${DAYS[slot.day_of_week] ?? "?"} ${String(hour).padStart(2, "0")}h`;
    });
}

export function pickDefaultCart(carts: Cart[], hint: RegExp): string | null {
  const hit = carts.find((cart) => hint.test(cart.title));
  return hit?.title ?? carts[0]?.title ?? null;
}

export function pickCart(carts: Cart[], hint: RegExp): Cart | null {
  return carts.find((cart) => hint.test(cart.title)) ?? null;
}

export function pickProgCart(carts: Cart[]): Cart | null {
  return (
    pickCart(carts, /prog/i) ??
    carts.find((cart) => !/jingle|pub/i.test(cart.title)) ??
    null
  );
}

export function pickPubCart(carts: Cart[]): Cart | null {
  return (
    pickCart(carts, /pub|spot/i) ??
    carts.find((cart) => !/prog|jingle/i.test(cart.title)) ??
    null
  );
}

function hourMark(minute: number): string {
  if (minute >= 1440) return "24h";
  const hour = Math.floor(Math.max(0, minute) / 60);
  const min = Math.max(0, minute) % 60;
  return min ? `${hour}h${String(min).padStart(2, "0")}` : `${hour}h`;
}

export function weekGridSummary(
  slots: Array<{ day_of_week: number; minute: number; clock?: string | null }>,
): string {
  const ranges = daypartRanges(slots);
  if (!ranges.length) return "Pas encore dans la grille de la semaine.";
  type Agg = { name: string; start: number; end: number; days: Set<number> };
  const grouped = new Map<string, Agg>();
  for (const range of ranges) {
    const name = (range.slot.clock || "").trim() || "Rotation";
    const key = `${name}|${range.start}|${range.end}`;
    const row = grouped.get(key) ?? {
      name,
      start: range.start,
      end: range.end,
      days: new Set<number>(),
    };
    row.days.add(range.day);
    grouped.set(key, row);
  }
  const byName = new Map<string, Agg[]>();
  for (const row of grouped.values()) {
    const list = byName.get(row.name) ?? [];
    list.push(row);
    byName.set(row.name, list);
  }
  const parts: string[] = [];
  for (const [name, rows] of byName) {
    const allWeek = rows.every((row) => row.days.size === 7);
    const windows = [...rows]
      .sort((a, b) => a.start - b.start)
      .map((row) => `${hourMark(row.start)}–${hourMark(row.end)}`)
      .join(" et ");
    if (allWeek && /pub/i.test(name)) parts.push(`pubs ${windows}`);
    else if (allWeek) parts.push(`Tous les jours ${windows}`);
    else {
      const days = [...new Set(rows.flatMap((row) => [...row.days]))]
        .sort((left, right) => left - right)
        .map((day) => DAYS[day] ?? "?")
        .join(", ");
      parts.push(`${days} ${windows}`);
    }
  }
  parts.sort((left, right) => Number(left.startsWith("pubs")) - Number(right.startsWith("pubs")));
  return parts.join(" · ");
}

export function pickDefaultCategory(categories: Category[]): string | null {
  const hit = categories.find((cat) => /rotation/i.test(cat.name));
  return hit?.name ?? categories[0]?.name ?? null;
}

export function withoutLibrarySteps(motif: ClockPosition[]): ClockPosition[] {
  return motif.filter((step) => step.kind !== "musique");
}

export function defaultMotif(
  carts: Cart[],
  _categories: Category[] = [],
  fallback: string | null = null,
): ClockPosition[] {
  const jingle = pickCart(carts, /jingle/i);
  const prog = pickProgCart(carts);
  const steps: ClockPosition[] = [];
  if (jingle) {
    steps.push({
      kind: "jingle",
      when: "sequential",
      cart: jingle.title,
      cart_id: jingle.id,
      category: null,
      fallback_cart: fallback,
    });
  }
  if (prog && prog.id !== jingle?.id) {
    steps.push({
      kind: "son",
      when: "sequential",
      cart: prog.title,
      cart_id: prog.id,
      category: null,
      fallback_cart: fallback,
    });
  }
  return steps;
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

export function positionUsesCart(
  pos: ClockPosition,
  cart: { id: number; title: string },
): boolean {
  if (pos.cart_id != null && pos.cart_id === cart.id) return true;
  return titlesMatch(pos.cart, cart.title);
}

export function clockHasCart(clock: Clock, cart: { id: number; title: string }): boolean {
  return [...clock.motif, ...clock.anchors].some((pos) => positionUsesCart(pos, cart));
}

export function clockCartUsages(
  clocks: Clock[],
  cart: { id: number; title: string },
): ClockCartUsage[] {
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

export function clockAtWall(
  clocks: Clock[],
  slots: Slot[],
  now: Date = new Date(),
  rundownClockName?: string | null,
): Clock | null {
  if (!clocks.length) return null;
  const ranges = daypartRanges(slots);
  const { hour, minute } = parisParts(now);
  const range = rangeAtMinute(ranges, parisWeekdayMon0(now), hour * 60 + minute);
  const slot = range?.slot;
  const fromSlot = slot
    ? clocks.find((clock) => clock.id === slot.clock_id || clock.name === slot.clock)
    : null;
  if (fromSlot) return fromSlot;
  if (rundownClockName) {
    const fromName = clocks.find((clock) => clock.name === rundownClockName);
    if (fromName) return fromName;
  }
  return clocks[0] ?? null;
}

export function guessCartKind(title: string): Exclude<PositionKind, "musique"> {
  const text = title.toLowerCase();
  if (/jingle/.test(text)) return "jingle";
  if (/pub/.test(text)) return "pub";
  return "son";
}

export function cartTitleKnown(title: string | null | undefined, carts: Cart[]): boolean {
  const wanted = (title || "").trim().toLowerCase();
  if (!wanted) return false;
  return carts.some((cart) => cart.title.trim().toLowerCase() === wanted);
}

export function motifStepMissingCart(step: ClockPosition, carts: Cart[]): boolean {
  if (step.kind === "musique") return false;
  const title = (step.cart || "").trim();
  if (!title) return true;
  return !cartTitleKnown(title, carts);
}

export function vacantMotifIndexes(
  clock: Clock,
  kind: PositionKind,
  carts: Cart[],
): number[] {
  return clock.motif.flatMap((step, index) =>
    step.kind === kind && motifStepMissingCart(step, carts) ? [index] : [],
  );
}

export function clockUsageLine(usages: ClockCartUsage[]): string {
  const inHour = hourUsages(usages);
  if (!inHour.length) return "pas dans l’Auto-DJ";
  const roles = [
    ...new Set(
      inHour.map((usage) =>
        usage.kind === "secours" ? "secours" : kindLabel(usage.kind),
      ),
    ),
  ];
  return `Dans Auto-DJ · ${roles.join(" · ")}`;
}

export type AutodjCartRow = {
  cart: Cart;
  kind: PositionKind | "secours";
  role: string;
  clockNames: string[];
  isDefaultProgramme: boolean;
};

export function autodjCartRows(clocks: Clock[], carts: Cart[]): AutodjCartRow[] {
  const rows: AutodjCartRow[] = [];
  for (const cart of carts) {
    const usages = hourUsages(clockCartUsages(clocks, cart));
    if (!usages.length) continue;
    const kind = usages[0].kind;
    rows.push({
      cart,
      kind,
      role: kind === "secours" ? "Secours" : kindLabel(kind),
      clockNames: [...new Set(usages.map((usage) => usage.clockName))],
      isDefaultProgramme: kind === "son" && /prog/i.test(cart.title),
    });
  }
  const rank = (row: AutodjCartRow) =>
    row.kind === "jingle" ? 0 : row.kind === "son" ? 1 : row.kind === "pub" ? 2 : 3;
  return rows.sort((a, b) => rank(a) - rank(b) || a.cart.title.localeCompare(b.cart.title, "fr"));
}

export function cartsOutsideClock(clock: Clock, carts: Cart[]): Cart[] {
  return carts.filter((cart) => !clockHasCart(clock, cart));
}

export type CartWhere = "hour" | "timed" | "manual";

export function shortClockName(name: string): string {
  return name.trim().split(/\s+/)[0] || name;
}

export function hourUsages(usages: ClockCartUsage[]): ClockCartUsage[] {
  return usages.filter((usage) => usage.where !== "fallback");
}

export function hasPileSchedule(cart: {
  schedule_mode: string;
  schedule_hour: string;
  schedule_minute: string;
  schedule_summary?: string;
}): boolean {
  if (cart.schedule_mode === "jingles") return /^\d+$/.test(cart.schedule_minute);
  if (/^\d+$/.test(cart.schedule_hour) || /^\d+$/.test(cart.schedule_minute)) return true;
  return /proch\./i.test(cart.schedule_summary || "");
}

function pileClockLabel(cart: Cart): string {
  if (/^\d+$/.test(cart.schedule_hour)) {
    return `${padClock(cart.schedule_hour)}:${padClock(cart.schedule_minute)}`;
  }
  if (/^\d+$/.test(cart.schedule_minute)) {
    return `:${padClock(cart.schedule_minute)}`;
  }
  const hit = (cart.schedule_summary || "").match(/(\d{1,2}:\d{2})/);
  return hit?.[1] ?? cart.schedule_summary;
}

export function cartWhere(usages: ClockCartUsage[], cart: Cart): CartWhere {
  if (hourUsages(usages).length) return "hour";
  if (hasPileSchedule(cart)) return "timed";
  return "manual";
}

function padClock(value: string, fallback = "00"): string {
  if (!/^\d+$/.test(value)) return fallback;
  return value.padStart(2, "0");
}

export function cartWhereLine(usages: ClockCartUsage[], cart: Cart): string {
  const inHour = hourUsages(usages);
  if (inHour.length) {
    const usage = inHour[0];
    const kind = usage.kind === "secours" ? "secours" : kindLabel(usage.kind);
    if (usage.where === "motif" && usage.index != null) {
      return `Dans Auto-DJ · ${kind} #${usage.index + 1}`;
    }
    if (usage.where === "anchor" && usage.minute != null) {
      return `Dans Auto-DJ · ${kind} :${String(usage.minute).padStart(2, "0")}`;
    }
    return `Dans Auto-DJ · ${kind}`;
  }
  if (hasPileSchedule(cart)) {
    if (cart.schedule_mode === "jingles") {
      return `À :${padClock(cart.schedule_minute)}, pas dans l’Auto-DJ`;
    }
    return `À ${pileClockLabel(cart)} pile, pas dans l’Auto-DJ`;
  }
  return "Pas dans l’Auto-DJ — Maintenant le joue une fois";
}

export function recipeKindLabel(kind: PositionKind): string {
  return kindLabel(kind);
}

export type ClockRecipeCase = {
  key: string;
  kind: PositionKind;
  role: string;
  title: string;
  cartId: number | null;
  emptyHint: string | null;
  highlighted: boolean;
  where: "motif" | "anchor";
};

function cartForPosition(pos: ClockPosition, carts: Cart[]): Cart | undefined {
  if (pos.cart_id != null) {
    const byId = carts.find((cart) => cart.id === pos.cart_id);
    if (byId) return byId;
  }
  const title = (pos.cart || "").trim();
  if (!title) return undefined;
  return carts.find((cart) => titlesMatch(cart.title, title));
}

export function clockRecipeCases(
  clock: Clock,
  carts: Cart[],
  openCart?: { id: number; title: string } | null,
): ClockRecipeCase[] {
  const row = (pos: ClockPosition, where: "motif" | "anchor", index: number): ClockRecipeCase => {
    const highlighted = openCart ? positionUsesCart(pos, openCart) : false;
    if (pos.kind === "musique") {
      return {
        key: `${where}-${index}`,
        kind: pos.kind,
        role: recipeKindLabel(pos.kind),
        title: pos.category?.trim() ? `Catégorie ${pos.category.trim()}` : "Catégorie à choisir",
        cartId: null,
        emptyHint: null,
        highlighted,
        where,
      };
    }
    const linked = cartForPosition(pos, carts);
    const title = linked?.title || pos.cart?.trim() || "—";
    let emptyHint: string | null = null;
    if (linked && linked.sounds.length === 0) emptyHint = "vide — importe des titres";
    else if (!linked) emptyHint = "cart manquant";
    return {
      key: `${where}-${index}`,
      kind: pos.kind,
      role: recipeKindLabel(pos.kind),
      title,
      cartId: linked?.id ?? pos.cart_id ?? null,
      emptyHint,
      highlighted,
      where,
    };
  };
  return [
    ...clock.motif.map((pos, index) => row(pos, "motif", index)),
    ...clock.anchors.map((pos, index) => row(pos, "anchor", index)),
  ];
}
