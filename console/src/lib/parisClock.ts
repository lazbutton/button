import { useEffect, useState } from "react";

const PARIS: Intl.DateTimeFormatOptions = {
  timeZone: "Europe/Paris",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  weekday: "short",
  day: "2-digit",
  month: "2-digit",
  hourCycle: "h23",
};

function part(
  parts: Intl.DateTimeFormatPart[],
  type: Intl.DateTimeFormatPartTypes,
): string {
  return parts.find((p) => p.type === type)?.value ?? "";
}

export type ParisParts = {
  weekday: string;
  day: string;
  month: string;
  hour: number;
  minute: number;
  second: number;
  clock: string;
  date: string;
};

export function parisParts(date: Date): ParisParts {
  const parts = new Intl.DateTimeFormat("fr-FR", PARIS).formatToParts(date);
  const hour = part(parts, "hour");
  const minute = part(parts, "minute");
  const second = part(parts, "second");
  return {
    weekday: part(parts, "weekday"),
    day: part(parts, "day"),
    month: part(parts, "month"),
    hour: Number(hour),
    minute: Number(minute),
    second: Number(second),
    clock: `${hour}:${minute}:${second}`,
    date: `${part(parts, "weekday")} ${part(parts, "day")}/${part(parts, "month")}`,
  };
}

export function nextAnchor(date: Date): { label: ":20" | ":40"; remainingSec: number } {
  const { minute, second } = parisParts(date);
  const secOfHour = minute * 60 + second;
  const t20 = 20 * 60;
  const t40 = 40 * 60;
  const hourLen = 60 * 60;
  if (secOfHour < t20) return { label: ":20", remainingSec: t20 - secOfHour };
  if (secOfHour < t40) return { label: ":40", remainingSec: t40 - secOfHour };
  return { label: ":20", remainingSec: hourLen - secOfHour + t20 };
}

export function formatMmSs(totalSec: number): string {
  const sec = Math.max(0, Math.round(totalSec));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export function formatHhMmSs(totalSec: number): string {
  const sec = Math.max(0, Math.round(totalSec));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h > 0) return `${h} h ${m} min`;
  return `${m} min`;
}

export function conducteurHorizonMin(date: Date = new Date()): number {
  const { hour, minute } = parisParts(date);
  const untilMidnight = 24 * 60 - (hour * 60 + minute);
  return Math.min(18 * 60, Math.max(4 * 60, untilMidnight));
}

/** Lundi = 0 … dimanche = 6, fuseau Europe/Paris. */
export function parisWeekdayMon0(date: Date): number {
  const weekday = new Intl.DateTimeFormat("en-US", {
    timeZone: "Europe/Paris",
    weekday: "long",
  }).format(date);
  const order: Record<string, number> = {
    Monday: 0,
    Tuesday: 1,
    Wednesday: 2,
    Thursday: 3,
    Friday: 4,
    Saturday: 5,
    Sunday: 6,
  };
  return order[weekday] ?? 0;
}

export function useParisNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return now;
}
