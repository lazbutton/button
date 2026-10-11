import { formatDayMinute } from "./clockCss";
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

export function nextEmissionLabel(next: EmissionNext, dayNames: readonly string[]): string {
  const when =
    next.start_minute != null
      ? minuteToClock(next.start_minute)
      : next.at.includes("T")
        ? next.at.split("T")[1]?.slice(0, 5)
        : next.at;
  const day = next.day_of_week != null ? dayNames[next.day_of_week] : null;
  return [day, when, next.title].filter(Boolean).join(" · ");
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
