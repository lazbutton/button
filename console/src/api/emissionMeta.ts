import { parisWall, weekdayOf } from "./agendaView.ts";
import { formatDayMinute } from "./clockCss.ts";
import type { Emission, EmissionNext, LiveSnapshot } from "./types";

export function isHarborSource(source: string | undefined): boolean {
  const text = (source || "").toLowerCase();
  return text.includes("stream") || text.includes("harbor");
}

export function harborIsLive(live: LiveSnapshot | null): boolean {
  if (!live || live.status === "offline") return false;
  return isHarborSource(live.source);
}

export function minuteToClock(minute: number): string {
  return formatDayMinute(minute);
}

export function clockToMinute(value: string): number | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (!Number.isFinite(hour) || !Number.isFinite(minute)) return null;
  if (hour === 24 && minute === 0) return 1440;
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  return hour * 60 + minute;
}

export function emissionWindowLabel(row: Pick<Emission, "start_minute" | "end_minute">): string {
  const start = row.start_minute ?? 0;
  const end = row.end_minute ?? start;
  return `${minuteToClock(start)} → ${minuteToClock(end)}`;
}

/**
 * « Lun 16 · 20:00 » : le jour, sa date et l'heure de Paris où commence le prochain direct,
 * émission hebdo ou direct de l'Agenda. La date dit aussi qu'une émission annulée ce soir
 * laisse la place à celle de la semaine d'après.
 */
export function nextEmissionWhen(next: EmissionNext, dayNames: readonly string[]): string {
  const at = Date.parse(next.at);
  if (Number.isFinite(at)) {
    const wall = parisWall(new Date(at));
    return `${dayNames[weekdayOf(wall.day)]} ${Number(wall.day.slice(8, 10))} · ${minuteToClock(wall.minute)}`;
  }
  // Sans heure lisible : le jour et l'heure de l'émission hebdo, sans date.
  const day = next.day_of_week != null ? dayNames[next.day_of_week] : null;
  const time = next.start_minute != null ? minuteToClock(next.start_minute) : null;
  return [day, time].filter(Boolean).join(" · ");
}

export function nextEmissionLabel(next: EmissionNext, dayNames: readonly string[]): string {
  return [nextEmissionWhen(next, dayNames), next.title].filter(Boolean).join(" · ");
}

export function emissionPillLabel(
  current: { title: string; state?: string; start_minute?: number | null } | null,
  next: EmissionNext | null,
  dayNames: readonly string[],
): string | null {
  if (current) {
    const time = current.start_minute != null ? minuteToClock(current.start_minute) : null;
    const waiting = current.state === "waiting" ? "en attente · " : "";
    return [time, `${waiting}${current.title}`].filter(Boolean).join(" ");
  }
  if (next) return nextEmissionLabel(next, dayNames);
  return null;
}
