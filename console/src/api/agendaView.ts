import type { AirStatus, Diffusion, Prep, TodoLine, WeeklyOccurrence } from "./agenda";

/** Paris calendar days ("2026-11-07"), Paris walls, and how the Agenda draws them. No runtime import. */

export const DAY_SHORT_FR = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
export const DAY_LONG_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"];
export const MONTHS_FR = [
  "janvier",
  "février",
  "mars",
  "avril",
  "mai",
  "juin",
  "juillet",
  "août",
  "septembre",
  "octobre",
  "novembre",
  "décembre",
];
const MONTHS_SHORT_FR = [
  "janv.",
  "févr.",
  "mars",
  "avr.",
  "mai",
  "juin",
  "juil.",
  "août",
  "sept.",
  "oct.",
  "nov.",
  "déc.",
];

export const STEP_MINUTES = 15;
const DAY_MS = 86_400_000;

const PARIS_FORMAT = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Europe/Paris",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export type Wall = { day: string; minute: number };

/** A Paris wall reading of an instant: its day, and the minute of that day. */
export function parisWall(value: Date | string): Wall {
  const date = typeof value === "string" ? new Date(value) : value;
  const parts = PARIS_FORMAT.formatToParts(date);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "00";
  return {
    day: `${get("year")}-${get("month")}-${get("day")}`,
    minute: Number(get("hour")) * 60 + Number(get("minute")),
  };
}

function dayToUtc(day: string): number {
  const [year, month, date] = day.split("-").map(Number);
  return Date.UTC(year, month - 1, date);
}

function utcToDay(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

export function addDays(day: string, count: number): string {
  return utcToDay(dayToUtc(day) + count * DAY_MS);
}

/** Monday 0 … Sunday 6. */
export function weekdayOf(day: string): number {
  return (new Date(dayToUtc(day)).getUTCDay() + 6) % 7;
}

export function mondayOf(day: string): string {
  return addDays(day, -weekdayOf(day));
}

export function daysBetween(from: string, to: string): number {
  return Math.round((dayToUtc(to) - dayToUtc(from)) / DAY_MS);
}

export function weekDays(monday: string): string[] {
  return Array.from({ length: 7 }, (_, index) => addDays(monday, index));
}

function dayNumber(day: string): number {
  return Number(day.slice(8, 10));
}

function monthIndex(day: string): number {
  return Number(day.slice(5, 7)) - 1;
}

/** « Lun 12 » */
export function dayShortLabel(day: string): string {
  return `${DAY_SHORT_FR[weekdayOf(day)]} ${dayNumber(day)}`;
}

/** « lundi 12 octobre » */
export function dayLongLabel(day: string): string {
  return `${DAY_LONG_FR[weekdayOf(day)]} ${dayNumber(day)} ${MONTHS_FR[monthIndex(day)]}`;
}

/** « 12 – 18 octobre 2026 », « 28 sept. – 4 oct. 2026 », « 28 déc. 2026 – 3 janv. 2027 » */
export function weekLabel(monday: string): string {
  const sunday = addDays(monday, 6);
  const sameYear = monday.slice(0, 4) === sunday.slice(0, 4);
  if (monthIndex(monday) === monthIndex(sunday) && sameYear) {
    return `${dayNumber(monday)} – ${dayNumber(sunday)} ${MONTHS_FR[monthIndex(sunday)]} ${sunday.slice(0, 4)}`;
  }
  const left = `${dayNumber(monday)} ${MONTHS_SHORT_FR[monthIndex(monday)]}${sameYear ? "" : ` ${monday.slice(0, 4)}`}`;
  return `${left} – ${dayNumber(sunday)} ${MONTHS_SHORT_FR[monthIndex(sunday)]} ${sunday.slice(0, 4)}`;
}

export function hhmm(minute: number): string {
  const bounded = Math.max(0, Math.min(1440, Math.round(minute)));
  if (bounded === 1440) return "24:00";
  return `${String(Math.floor(bounded / 60)).padStart(2, "0")}:${String(bounded % 60).padStart(2, "0")}`;
}

export function timeLabel(iso: string): string {
  return hhmm(parisWall(iso).minute);
}

/** « 2 h », « 1 h 30 », « 45 min » */
export function durationLabel(minutes: number): string {
  const total = Math.max(0, Math.round(minutes));
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  if (!hours) return `${rest} min`;
  return rest ? `${hours} h ${String(rest).padStart(2, "0")}` : `${hours} h`;
}

export function secondsLabel(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours) return minutes ? `${hours} h ${String(minutes).padStart(2, "0")}` : `${hours} h`;
  if (minutes) return `${minutes} min`;
  return `${total} s`;
}

/** The Paris wall the server expects for a day and a minute (1440 is the next midnight). */
export function wallString(day: string, minute: number): string {
  const extra = Math.floor(minute / 1440);
  const inDay = minute - extra * 1440;
  return `${addDays(day, extra)}T${hhmm(inDay)}`;
}

export function snap(minute: number, step = STEP_MINUTES): number {
  return Math.round(minute / step) * step;
}

/** « samedi 24 octobre, 22:00 → 00:00 » */
export function rangeLabel(start: string, end: string): string {
  const from = parisWall(start);
  const to = parisWall(end);
  const sameNight = to.day === from.day || (to.minute === 0 && daysBetween(from.day, to.day) === 1);
  const tail = sameNight ? hhmm(to.minute) : `${dayLongLabel(to.day)}, ${hhmm(to.minute)}`;
  return `${dayLongLabel(from.day)}, ${hhmm(from.minute)} → ${tail}`;
}

export type Segment = { day: string; start: number; end: number; first: boolean; last: boolean };

/** Cut a span into one segment per Paris day it touches (wall minutes, 0 to 1440). */
export function segments(startIso: string, endIso: string): Segment[] {
  const from = parisWall(startIso);
  const to = parisWall(endIso);
  const out: Segment[] = [];
  let day = from.day;
  let guard = 0;
  while (guard < 3) {
    const start = day === from.day ? from.minute : 0;
    const finishing = day === to.day;
    const end = finishing ? to.minute : 1440;
    if (end > start) out.push({ day, start, end, first: day === from.day, last: finishing });
    if (finishing) break;
    day = addDays(day, 1);
    guard += 1;
  }
  if (out.length) out[out.length - 1].last = true;
  return out;
}

export type Tone = "ok" | "wait" | "warn" | "live" | "done" | "missed";

export type StatusChip = { label: string; tone: Tone; detail: string };

/** The one state a block shows: the antenna first, then the preparation. */
export function statusOf(row: Pick<Diffusion, "kind" | "air_status" | "air_reason" | "prep" | "prep_reason" | "overrun_seconds" | "stop_requested">): StatusChip {
  const air: AirStatus = row.air_status;
  if (air === "on_air") {
    return { label: row.stop_requested ? "Arrêt demandé" : "À l'antenne", tone: "live", detail: "" };
  }
  if (air === "aired") return { label: "Diffusée", tone: "done", detail: row.air_reason };
  if (air === "missed") return { label: "Manquée", tone: "missed", detail: row.air_reason };
  const prep: Prep = row.prep;
  if (prep === "pret") {
    if (row.kind === "set" && row.overrun_seconds) {
      return { label: "Prêt", tone: "warn", detail: `Dépasse de ${secondsLabel(row.overrun_seconds)}` };
    }
    return { label: "Prêt", tone: "ok", detail: "" };
  }
  if (prep === "analyse") return { label: "Analyse…", tone: "wait", detail: "" };
  if (prep === "a_revoir") return { label: "À revoir", tone: "warn", detail: row.prep_reason };
  return {
    label: row.kind === "live" ? "Sans animateur" : "Set attendu",
    tone: "wait",
    detail: "",
  };
}

export function todoFor(todo: TodoLine[]): Map<number, TodoLine> {
  return new Map(todo.map((line) => [line.diffusion_id, line]));
}

export function inviteLink(origin: string, token: string): string {
  return `${origin.replace(/\/+$/, "")}/invitation#${token}`;
}

/** The message a programmer pastes to the guest: date, Paris hours, deadline, link. */
export function inviteMessage(params: {
  station: string;
  guest: string;
  title: string;
  start: string;
  end: string;
  deadline: string;
  link: string;
}): string {
  const from = parisWall(params.start);
  const deadline = parisWall(params.deadline);
  const minutes = Math.round((new Date(params.end).getTime() - new Date(params.start).getTime()) / 60_000);
  return [
    `Salut ${params.guest} !`,
    `Ton créneau sur ${params.station} : « ${params.title} », ${dayLongLabel(from.day)} à ${hhmm(from.minute)} (heure de Paris), ${durationLabel(minutes)}.`,
    `Dépose ton set avant le ${dayLongLabel(deadline.day)}, ${hhmm(deadline.minute)}, ici : ${params.link}`,
    "Formats acceptés : mp3, flac, wav, aiff, ogg, opus, m4a. Le lien est personnel, garde-le pour toi.",
  ].join("\n");
}

/** Weekly shows of a day, without the ones a dated broadcast covers or a day off removes. */
export function visibleWeekly(rows: WeeklyOccurrence[], day: string): WeeklyOccurrence[] {
  return rows.filter((row) => row.date === day);
}

export type UpcomingEntry =
  | { type: "diffusion"; at: string; day: string; row: Diffusion }
  | { type: "weekly"; at: string; day: string; row: WeeklyOccurrence };

/** The list view: dated broadcasts and weekly shows, day by day, in time order. */
export function upcomingByDay(
  diffusions: Diffusion[],
  weekly: WeeklyOccurrence[],
  options: { from: string; onlyTodo?: Set<number> } = { from: "" },
): Array<{ day: string; entries: UpcomingEntry[] }> {
  const entries: UpcomingEntry[] = [];
  for (const row of diffusions) {
    if (options.onlyTodo && !options.onlyTodo.has(row.id)) continue;
    entries.push({ type: "diffusion", at: row.starts_at, day: parisWall(row.starts_at).day, row });
  }
  if (!options.onlyTodo) {
    for (const row of weekly) {
      if (row.replaced_by != null) continue;
      entries.push({ type: "weekly", at: row.starts_at, day: row.date, row });
    }
  }
  entries.sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());
  const groups: Array<{ day: string; entries: UpcomingEntry[] }> = [];
  for (const entry of entries) {
    if (options.from && entry.day < options.from) continue;
    const last = groups[groups.length - 1];
    if (last && last.day === entry.day) last.entries.push(entry);
    else groups.push({ day: entry.day, entries: [entry] });
  }
  return groups;
}

export function repeatLabel(rule: string, nth: number, weekday: number): string {
  if (rule === "weekly") return `Chaque ${DAY_LONG_FR[weekday]}`;
  if (rule === "biweekly") return `Un ${DAY_LONG_FR[weekday]} sur deux`;
  if (rule === "monthly") {
    const rank = nth === -1 ? "dernier" : nth === 1 ? "1er" : `${nth}e`;
    return `Chaque mois, le ${rank} ${DAY_LONG_FR[weekday]}`;
  }
  return "Une seule fois";
}

/** 1 to 4 for the rank of a weekday in its month, -1 when it is the last one. */
export function nthOfMonth(day: string): number {
  const nextWeek = addDays(day, 7);
  if (nextWeek.slice(5, 7) !== day.slice(5, 7)) return -1;
  return Math.min(4, Math.floor((dayNumber(day) - 1) / 7) + 1);
}

/** Minutes of the day under a pointer, snapped, from the column's geometry. */
export function minuteAt(offsetY: number, height: number, step = STEP_MINUTES): number {
  const ratio = Math.max(0, Math.min(1, offsetY / Math.max(1, height)));
  return Math.max(0, Math.min(1440, snap(ratio * 1440, step)));
}

export function guestLocalHint(startIso: string, endIso: string, timeZone: string): string {
  if (!timeZone || timeZone === "Europe/Paris") return "";
  const format = new Intl.DateTimeFormat("fr-FR", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const start = new Date(startIso);
  const end = new Date(endIso);
  const local = `${format.format(start)} → ${format.format(end)}`;
  const paris = `${timeLabel(startIso)} → ${timeLabel(endIso)}`;
  if (local === paris) return "";
  const city = timeZone.split("/").pop()?.replace(/_/g, " ") ?? timeZone;
  return `${local} chez toi (${city})`;
}
