/**
 * La page Conducteur, dans les mots de la console : heure type, bac, sélection
 * de titres, coupure. Ce que dit chaque ligne, d'où elle vient, et comment le
 * déroulé se découpe en heures. Pur : pas de React, testable en node.
 */
import { addDays, dayLongLabel, secondsLabel } from "./agendaView.ts";
import { itemStatusCode, queueItemSent, rundownCopy } from "./rundownLive.ts";
import type { RundownItem } from "./types";

/** La place d'une ligne dans le déroulé. */
export type LineRole = "past" | "now" | "next" | "later";

export type ChipTone = "live" | "danger" | "warn" | "plain";

/** Une mention à côté du titre, et sa raison quand le moteur la donne. */
export type LineChip = { label: string; tone: ChipTone; detail?: string };

// ---- L'heure d'une ligne -------------------------------------------------

export type LineWall = { day: string; hour: string; minute: string; second: string };

const ZONED = /(?:Z|[+-]\d{2}:?\d{2})$/i;
const NAIVE = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?/;
const PARIS = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Europe/Paris",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

/**
 * L'heure de Paris d'une ligne. Le moteur la donne sans fuseau, déjà à Paris :
 * elle se lit telle quelle, quel que soit le fuseau du navigateur. Une ligne
 * que la console bâtit elle-même, comme un direct, porte un fuseau.
 */
export function lineWall(at: string | Date): LineWall | null {
  if (at instanceof Date || ZONED.test(at)) {
    const date = at instanceof Date ? at : new Date(at);
    if (!Number.isFinite(date.getTime())) return null;
    const parts = PARIS.formatToParts(date);
    const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "00";
    return {
      day: `${get("year")}-${get("month")}-${get("day")}`,
      hour: get("hour"),
      minute: get("minute"),
      second: get("second"),
    };
  }
  const match = NAIVE.exec(at);
  if (!match) return null;
  return { day: match[1], hour: match[2], minute: match[3], second: match[4] ?? "00" };
}

/** « 11:36 », et les secondes à part, que la page montre en retrait. */
export function lineTime(at: string): { clock: string; seconds: string } {
  const wall = lineWall(at);
  if (!wall) return { clock: "—", seconds: "" };
  return { clock: `${wall.hour}:${wall.minute}`, seconds: `:${wall.second}` };
}

function wallMs(wall: LineWall): number {
  const [year, month, day] = wall.day.split("-").map(Number);
  return Date.UTC(year, month - 1, day, Number(wall.hour), Number(wall.minute), Number(wall.second));
}

/** Les secondes d'ici une heure du conducteur, lues toutes deux à Paris : le fuseau du navigateur n'y change rien. */
export function secondsUntil(at: string, now: Date): number | null {
  const target = lineWall(at);
  const current = lineWall(now);
  if (!target || !current) return null;
  return (wallMs(target) - wallMs(current)) / 1000;
}

/** L'heure de fin d'une ligne, « 13:39 », quand sa durée est connue. */
export function lineEnd(item: RundownItem): string | null {
  const wall = lineWall(item.at);
  const seconds = Number(item.duration);
  if (!wall || !Number.isFinite(seconds) || seconds <= 0) return null;
  const end = new Date(wallMs(wall) + seconds * 1000);
  return `${String(end.getUTCHours()).padStart(2, "0")}:${String(end.getUTCMinutes()).padStart(2, "0")}`;
}

/** « dans 26 min », « dans 1 h 05 », ou « maintenant ». */
export function untilLabel(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  if (total < 1) return "maintenant";
  return `dans ${secondsLabel(total)}`;
}

// ---- Ce que dit une ligne ------------------------------------------------

const KIND_NAMES: Record<string, string> = {
  musique: "Titre",
  jingle: "Jingle",
  pub: "Pub",
  son: "Programme",
  emission: "Émission",
};

/** Le type d'une ligne, dit comme dans les heures types. */
export function kindName(kind: string): string {
  return KIND_NAMES[kind] ?? "Son";
}

/** La pastille de type : les quatre couleurs du pupitre, et l'émission de l'Agenda à part. */
export function kindClass(kind: string): "musique" | "jingle" | "pub" | "son" | "emission" {
  if (kind === "musique" || kind === "jingle" || kind === "pub" || kind === "emission") return kind;
  return "son";
}

/** Le son d'une étape d'heure type porte son bac pour artiste : le bac va dans l'origine. */
function artistIsBac(item: RundownItem): boolean {
  const cart = item.cart?.trim();
  return Boolean(cart) && item.artist?.trim() === cart;
}

/** Le titre, puis l'artiste. Une ligne sans son dit ce qui manque. */
export function lineCopy(item: RundownItem): { title: string; artist: string } {
  if (item.kind === "musique" && itemStatusCode(item) === "failed" && !item.title?.trim()) {
    return { title: "Titre manquant", artist: "" };
  }
  if (artistIsBac(item)) {
    return { title: item.title?.trim() || item.resource?.trim() || "—", artist: "" };
  }
  const copy = rundownCopy(item);
  return { title: copy.title, artist: copy.artist ?? "" };
}

/** D'où vient la ligne : le pupitre, l'Agenda, un direct, sa sélection de titres ou son bac. */
export function lineOrigin(item: RundownItem): string {
  if (item.origin === "desk") return "Pupitre";
  if (item.origin === "agenda") return "Agenda";
  if (item.origin === "live" || item.queue === "stream") return "Direct";
  if (item.kind === "musique") return item.category?.trim() || "";
  const cart = item.cart?.trim() || "";
  return cart && cart !== lineCopy(item).title ? cart : "";
}

const REASONS: Record<string, string> = {
  "cart introuvable": "bac introuvable ou sans son",
  "bac en relais": "bac en relais : une heure type ne le lance pas",
  "aucun titre Beets": "aucun titre dans la sélection",
  "dépassé par une ancre dure": "une coupure pile suit de près",
  "file vidée": "file vidée",
  "retiré de la file": "retirée au pupitre",
  "commande expirée": "le playout ne l’a pas prise à temps",
};

/** La raison du moteur, dans les mots de la console. Un glissement ne se dit pas : la coupure le montre. */
export function reasonLabel(reason: string | null | undefined): string {
  const raw = (reason || "").trim();
  if (!raw || raw === "glissement") return "";
  return REASONS[raw] ?? raw;
}

/**
 * L'état d'une ligne, seulement quand il dit quelque chose : « prévu » sur
 * chaque ligne ne dit rien. Une ligne envoyée au playout dit « Déjà partie »,
 * comme au pupitre.
 */
export function lineStatus(item: RundownItem, role: LineRole): LineChip | null {
  const code = itemStatusCode(item);
  const reason = reasonLabel(item.reason);
  // Manquante, même à son heure : le bandeau la compte, la ligne dit pourquoi.
  if (code === "failed") {
    const fallback = item.kind === "musique" ? "aucun titre dans la sélection" : "bac introuvable ou sans son";
    return { label: "Manquant", tone: "danger", detail: reason || fallback };
  }
  if (role === "now") return { label: "À l’antenne", tone: "live" };
  if (code === "rescue") {
    return { label: "Secours", tone: "warn", detail: "le bac prévu n’a rien donné : son secours passe à sa place" };
  }
  if (code === "skipped") return { label: "Sautée", tone: "plain", detail: reason || undefined };
  if (code === "replaced") return { label: "Remplacée", tone: "plain", detail: reason || undefined };
  if (role !== "past" && queueItemSent(item)) return { label: "Déjà partie", tone: "plain" };
  return null;
}

/** « :00 · coupe pile », « :30 · attend la fin », comme dans l'heure type. */
export function cutLabel(anchor: { minute?: number | null; sync?: string | null }): string {
  const minute = anchor.minute != null ? `:${String(anchor.minute).padStart(2, "0")}` : "";
  const mode = anchor.sync === "dure" ? "coupe pile" : anchor.sync === "molle" ? "attend la fin" : "";
  return [minute, mode].filter(Boolean).join(" · ");
}

/** Une coupure de l'heure type, ou ce qu'est une émission de l'Agenda, et jusqu'à quand. */
export function lineCut(item: RundownItem): LineChip | null {
  if (item.kind === "emission" || item.origin === "agenda") {
    const end = lineEnd(item);
    return { label: item.queue === "stream" ? "Direct" : "Set", tone: "plain", detail: end ? `jusqu’à ${end}` : undefined };
  }
  if (item.when !== "anchored") return null;
  const mode = cutLabel({ sync: item.sync });
  const minute = item.minute != null ? ` :${String(item.minute).padStart(2, "0")}` : "";
  return { label: `Coupure${minute}`, tone: "plain", detail: mode || undefined };
}

// ---- Le déroulé ----------------------------------------------------------

/** Une ligne à sa place dans le déroulé. */
export type RundownLine = { item: RundownItem; role: LineRole };

/** Une marque avant une ligne : l'heure qui change, le jour, l'heure type qui commence. */
export type RundownMark = {
  /** « 11 h ». */
  hour: string;
  /** L'heure change ici ; sinon, seule l'heure type change, en cours d'heure. */
  newHour: boolean;
  /** « demain », « hier », ou le jour en toutes lettres, quand ce n'est pas aujourd'hui. */
  day: string;
  /** L'heure type qui commence ici, et sa plage. */
  clock: string;
  daypart: string;
  /** « 18:30 », l'heure de la ligne qui suit. */
  at: string;
};

export type RundownEntry =
  | { type: "mark"; key: string; mark: RundownMark }
  | { type: "line"; key: string; line: RundownLine };

const CLOSED = new Set(["played", "skipped", "replaced"]);

/**
 * Le moteur rend parfois une ligne deux fois, sous le même identifiant : close
 * dans le journal, et encore prévue dans la prévision. La ligne close l'emporte.
 * Un titre relancé, joué deux fois, garde ses deux lignes.
 */
export function withoutClosedTwins(items: RundownItem[]): RundownItem[] {
  const closed = new Set(
    items.filter((item) => item.id && CLOSED.has(itemStatusCode(item))).map((item) => item.id),
  );
  if (!closed.size) return items;
  const kept = items.filter((item) => !item.id || !closed.has(item.id) || CLOSED.has(itemStatusCode(item)));
  return kept.length === items.length ? items : kept;
}

/** Une clé stable : l'identifiant de la ligne, et son heure pour un titre relancé, qui garde le même. */
export function lineKey(item: RundownItem, index = 0): string {
  return item.id ? `${item.id}@${item.at}` : `${item.at}#${index}`;
}

function dayLabel(day: string, today: string): string {
  if (!day || !today || day === today) return "";
  if (day === addDays(today, 1)) return "demain";
  if (day === addDays(today, -1)) return "hier";
  return dayLongLabel(day);
}

/** Une ligne de l'heure type : ni le pupitre, ni l'Agenda, ni un direct. */
function fromClock(item: RundownItem): boolean {
  return !item.origin || item.origin === "clock";
}

/**
 * Le déroulé, découpé par heures. Une marque précède la première ligne, chaque
 * changement d'heure ou de jour, et chaque heure type qui commence. La première
 * heure type ne se marque pas : le résumé du haut la dit.
 */
export function rundownEntries(lines: RundownLine[], today: string): RundownEntry[] {
  const entries: RundownEntry[] = [];
  const seen = new Map<string, number>();
  let lastHour = "";
  let lastDay = "";
  let lastClock: string | null = null;
  lines.forEach((line, index) => {
    const { item } = line;
    const wall = lineWall(item.at);
    const hour = wall ? `${wall.day}T${wall.hour}` : lastHour;
    const clockName = fromClock(item) ? item.clock?.trim() || "" : "";
    const newHour = index === 0 || hour !== lastHour;
    const newClock = Boolean(clockName) && lastClock != null && clockName !== lastClock;
    let key = lineKey(item, index);
    const repeats = seen.get(key) ?? 0;
    seen.set(key, repeats + 1);
    if (repeats) key = `${key}~${repeats}`;
    if (newHour || newClock) {
      const day = wall?.day ?? lastDay;
      entries.push({
        type: "mark",
        key: `mark:${key}`,
        mark: {
          hour: wall ? `${Number(wall.hour)} h` : "",
          newHour,
          day: newHour ? dayLabel(day, today) : "",
          clock: newClock ? clockName : "",
          daypart: newClock ? item.daypart?.trim() || "" : "",
          at: wall ? `${wall.hour}:${wall.minute}` : "",
        },
      });
    }
    entries.push({ type: "line", key, line });
    lastHour = hour;
    if (wall) lastDay = wall.day;
    if (clockName) lastClock = clockName;
  });
  return entries;
}

/** Les lignes sans son : leur bac ou leur sélection ne donne rien. */
export function linesToRepair(items: RundownItem[]): RundownItem[] {
  return items.filter((item) => itemStatusCode(item) === "failed");
}

/** Ce que dit le bandeau des lignes à réparer. */
export function repairNotice(
  count: number,
  until: string | null,
  canRepair: boolean,
): { title: string; help: string } | null {
  if (count <= 0) return null;
  const one = count === 1;
  const title = `${one ? "1 ligne" : `${count} lignes`} à réparer${until ? ` d’ici ${until}` : ""}`;
  const why = one ? "Son bac ou sa sélection ne donne aucun son." : "Leur bac ou leur sélection ne donne aucun son.";
  const who = canRepair ? "" : one ? " Un programmateur peut la réparer ici." : " Un programmateur peut les réparer ici.";
  return { title, help: `${why}${who}` };
}

/** La prochaine heure type, si elle commence avant la fin du conducteur. */
export function nextClock(
  upcoming: RundownItem[],
  current: string | null | undefined,
): { name: string; at: string; daypart: string } | null {
  const now = (current || "").trim();
  for (const item of upcoming) {
    if (!fromClock(item)) continue;
    const name = item.clock?.trim() || "";
    if (name && name !== now) return { name, at: item.at, daypart: item.daypart?.trim() || "" };
  }
  return null;
}

/** L'identifiant de l'heure type en cours, pour l'ouvrir dans Programmation. */
export function clockIdOf(items: RundownItem[], name: string | null | undefined): number | null {
  const wanted = (name || "").trim();
  if (!wanted) return null;
  const found = items.find((item) => fromClock(item) && item.clock?.trim() === wanted && item.clock_id != null);
  return found?.clock_id ?? null;
}

/** Jusqu'où va le conducteur : l'heure de sa dernière ligne. */
export function planEnd(items: RundownItem[]): string | null {
  const last = items.at(-1);
  if (!last) return null;
  const { clock } = lineTime(last.at);
  return clock === "—" ? null : clock;
}
