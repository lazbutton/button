import { formatWhen } from "./updates.ts";

/** Where a title went on air from, as the engine says it (FON-76). */
export type PlayOrigin = "autodj" | "bac" | "agenda" | "autre";

/** The plays of a title, read in the air log: 90 days, the last ones first. */
export type TitlePlays = {
  days: number;
  count: number;
  by_origin: Record<PlayOrigin, number>;
  recent: Array<{ on_air: string | null; origin: PlayOrigin; cart: { id: number; title: string } | null }>;
};

const ORIGIN_LABELS: Record<PlayOrigin, string> = {
  autodj: "Auto-DJ",
  bac: "Bac",
  agenda: "Agenda",
  autre: "Autre",
};

/** « Passé 3 fois en 90 jours », « Pas passé en 90 jours ». */
export function playsHeadline(plays: Pick<TitlePlays, "count" | "days">): string {
  if (plays.count === 0) return `Pas passé à l'antenne en ${plays.days} jours`;
  return `Passé ${plays.count === 1 ? "une fois" : `${plays.count.toLocaleString("fr-FR")} fois`} en ${plays.days} jours`;
}

/** « Auto-DJ 2 · Bac 1 », the origins that count, in their order. */
export function playsOrigins(plays: Pick<TitlePlays, "by_origin">): string {
  return (Object.keys(ORIGIN_LABELS) as PlayOrigin[])
    .filter((origin) => (plays.by_origin?.[origin] ?? 0) > 0)
    .map((origin) => `${ORIGIN_LABELS[origin]} ${plays.by_origin[origin]}`)
    .join(" · ");
}

/** One play: « hier à 14:03 », and where from: « Auto-DJ », « Bac Nuit douce », « Agenda ». */
export function playLine(play: TitlePlays["recent"][number], now: Date = new Date()): { when: string; from: string } {
  const from = play.origin === "bac" && play.cart ? `Bac « ${play.cart.title} »` : ORIGIN_LABELS[play.origin] ?? "Autre";
  return { when: formatWhen(play.on_air, now), from };
}
