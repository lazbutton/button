import type { Clock, ClockPosition, PositionKind, Slot } from "./types";

/** The four kinds of step, as the Programmation page names them. */
export const STEP_KINDS: {
  kind: PositionKind;
  label: string;
  hint: string;
  source: "cart" | "selection";
}[] = [
  { kind: "jingle", label: "Jingle", hint: "Un son court d'habillage, tiré d'un bac.", source: "cart" },
  { kind: "musique", label: "Titres", hint: "Un titre de la banque, tiré d'une sélection.", source: "selection" },
  { kind: "son", label: "Programme", hint: "Un son d'un bac : chronique, programme, nappe.", source: "cart" },
  { kind: "pub", label: "Pub", hint: "Le contenu d'un bac de pubs.", source: "cart" },
];

export function stepKindLabel(kind: PositionKind): string {
  return STEP_KINDS.find((item) => item.kind === kind)?.label ?? kind;
}

export function usesSelection(kind: PositionKind): boolean {
  return kind === "musique";
}

export const DAY_SHORT = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"] as const;
export const DAY_LONG = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"] as const;
export const DAY_LETTER = ["L", "M", "M", "J", "V", "S", "D"] as const;

/** Minutes since midnight -> 07:30. 1440 reads 24:00. */
export function hhmm(minute: number): string {
  if (minute >= 1440) return "24:00";
  const safe = Math.max(0, Math.round(minute));
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
}

/** A minute of the hour -> :05. */
export function minuteMark(minute: number): string {
  return `:${String(Math.max(0, Math.min(59, Math.round(minute)))).padStart(2, "0")}`;
}

/** 07:30 -> 450. 24:00 is accepted for the end of a day. */
export function parseHhmm(text: string): number | null {
  const match = /^(\d{1,2}):(\d{2})$/.exec(text.trim());
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour === 24 && minute === 0) return 1440;
  if (hour > 23 || minute > 59) return null;
  return hour * 60 + minute;
}

/** 3 h 05, 45 min, 7 h. */
export function spanLabel(minutes: number): string {
  const span = Math.max(0, Math.round(minutes));
  const hours = Math.floor(span / 60);
  const rest = span % 60;
  if (!hours) return `${rest} min`;
  return rest ? `${hours} h ${String(rest).padStart(2, "0")}` : `${hours} h`;
}

/** [0,1,2,3,4] -> Lun–Ven ; every day -> Tous les jours ; [0,2,4] -> Lun, Mer, Ven. */
export function daySetLabel(days: number[]): string {
  const sorted = [...new Set(days)].filter((day) => day >= 0 && day <= 6).sort((a, b) => a - b);
  if (!sorted.length) return "";
  if (sorted.length === 7) return "Tous les jours";
  const parts: string[] = [];
  let start = sorted[0];
  let previous = sorted[0];
  const close = () => {
    if (previous - start >= 2) parts.push(`${DAY_SHORT[start]}–${DAY_SHORT[previous]}`);
    else if (previous > start) parts.push(`${DAY_SHORT[start]}, ${DAY_SHORT[previous]}`);
    else parts.push(DAY_SHORT[start]);
  };
  for (const day of sorted.slice(1)) {
    if (day === previous + 1) {
      previous = day;
      continue;
    }
    close();
    start = day;
    previous = day;
  }
  close();
  return parts.join(", ");
}

/** A stretch of one day played by one heure type: consecutive changes to the same one read as one. */
export type Run = {
  day: number;
  start: number;
  end: number;
  clockId: number | null;
  clockName: string;
  /** The change that starts the run first, then the redundant ones inside it. */
  slots: Slot[];
};

export function weekRuns(slots: Slot[]): Run[] {
  const runs: Run[] = [];
  for (let day = 0; day < 7; day += 1) {
    const daySlots = slots.filter((slot) => slot.day_of_week === day).sort((a, b) => a.minute - b.minute);
    daySlots.forEach((slot, index) => {
      const end = daySlots[index + 1]?.minute ?? 1440;
      const last = runs.at(-1);
      if (last && last.day === day && last.end === slot.minute && last.clockId === slot.clock_id) {
        last.end = end;
        last.slots.push(slot);
        return;
      }
      runs.push({
        day,
        start: slot.minute,
        end,
        clockId: slot.clock_id,
        clockName: slot.clock?.trim() || "",
        slots: [slot],
      });
    });
  }
  return runs;
}

/** Changes that repeat the heure type already playing: the page merges them away. */
export function redundantSlotIds(slots: Slot[]): number[] {
  return weekRuns(slots).flatMap((run) => run.slots.slice(1).map((slot) => slot.id));
}

export function runAt(runs: Run[], day: number, minute: number): Run | null {
  return runs.find((run) => run.day === day && run.start <= minute && minute < run.end) ?? null;
}

/** The next run to start after this moment, this week, wrapping to next week. */
export function nextRun(runs: Run[], day: number, minute: number): Run | null {
  const later = runs.filter((run) => run.day === day && run.start > minute).sort((a, b) => a.start - b.start)[0];
  if (later) return later;
  for (let offset = 1; offset <= 7; offset += 1) {
    const next = (day + offset) % 7;
    const first = runs.filter((run) => run.day === next).sort((a, b) => a.start - b.start)[0];
    if (first) return first;
  }
  return null;
}

/** Where an heure type plays in the week, one line per time window: « Lun–Ven 07:00 → 20:00 ». */
export function clockWeekUsage(slots: Slot[], clockId: number): string[] {
  const windows = new Map<string, { start: number; end: number; days: number[] }>();
  for (const run of weekRuns(slots)) {
    if (run.clockId !== clockId) continue;
    const key = `${run.start}-${run.end}`;
    const row = windows.get(key) ?? { start: run.start, end: run.end, days: [] };
    row.days.push(run.day);
    windows.set(key, row);
  }
  return [...windows.values()]
    .sort((a, b) => a.start - b.start || a.days[0] - b.days[0])
    .map((row) => `${daySetLabel(row.days)} ${hhmm(row.start)} → ${hhmm(row.end)}`);
}

/** Colours told apart in the week; an heure type keeps its colour while the list does not change. */
export const CLOCK_TINTS = ["blue", "amber", "violet", "teal", "crimson", "grass", "orange", "cyan", "plum", "brown"];

export function clockTints(clocks: { id: number }[]): Map<number, string> {
  const tints = new Map<number, string>();
  [...clocks]
    .sort((a, b) => a.id - b.id)
    .forEach((clock, index) => tints.set(clock.id, CLOCK_TINTS[index % CLOCK_TINTS.length]));
  return tints;
}

/** Clocks find nothing by case: two heures types or two sélections cannot share a name. */
export function nameTaken(name: string, others: string[]): boolean {
  const wanted = name.trim().toLocaleLowerCase("fr");
  return Boolean(wanted) && others.some((other) => other.trim().toLocaleLowerCase("fr") === wanted);
}

/** « Jour habillé » -> « Jour habillé (copie) », then (copie 2)… */
export function copyName(name: string, taken: string[]): string {
  const base = `${name.trim()} (copie)`;
  if (!nameTaken(base, taken)) return base;
  for (let index = 2; index < 100; index += 1) {
    const next = `${name.trim()} (copie ${index})`;
    if (!nameTaken(next, taken)) return next;
  }
  return base;
}

/** Steps without ids: a copy must not steal the positions of the original. */
export function copySteps(rows: ClockPosition[]): ClockPosition[] {
  return rows.map((row) => {
    const copy = { ...row };
    delete copy.id;
    return copy;
  });
}

/** Jingle → Titres ×3, for a list line. */
export function stepsSummary(clock: Pick<Clock, "motif">): string {
  const parts: { label: string; count: number }[] = [];
  for (const step of clock.motif) {
    const label = stepKindLabel(step.kind);
    const last = parts.at(-1);
    if (last && last.label === label) last.count += 1;
    else parts.push({ label, count: 1 });
  }
  return parts.map((part) => (part.count > 1 ? `${part.label} ×${part.count}` : part.label)).join(" → ");
}

export function cutsSummary(clock: Pick<Clock, "anchors">): string {
  const minutes = clock.anchors
    .map((row) => row.minute)
    .filter((minute): minute is number => minute != null)
    .sort((a, b) => a - b);
  return minutes.length ? minutes.map(minuteMark).join(" ") : "";
}

/** The engine answers in English; the page speaks French. */
export function engineErrorText(message: string | null | undefined, fallback: string): string {
  const text = (message || "").trim();
  if (!text) return fallback;
  const known: [RegExp, string][] = [
    [/^Clock .* already exists/i, "Une heure type porte déjà ce nom."],
    [/^Category .* already exists/i, "Une sélection porte déjà ce nom."],
    [/chevauche une autre emission/i, "Ce créneau chevauche une autre émission en direct."],
    [/a clock needs a sequential motif/i, "Une heure type garde au moins une étape."],
    [/duplicate anchor minute/i, "Il y a déjà une coupure à cette minute."],
    [/assigned to a daypart/i, "Cette heure type est posée dans la semaine : retire-la d'abord des plages."],
    [/slot is already scheduled/i, "Il y a déjà un changement d'horloge à cette heure ce jour-là."],
    [/midnight slot cannot be moved/i, "Le changement de minuit ne se déplace pas."],
    [/midnight slot is required/i, "Le changement de minuit est obligatoire."],
    [
      /changed since version/i,
      "Cet élément vient d'être modifié ailleurs. La page s'est mise à jour : refais ton geste.",
    ],
    [/unknown category/i, "Cette sélection de titres n'existe plus."],
    [/Unknown cart/i, "Ce bac n'existe plus."],
    [/unknown clock_id/i, "Cette heure type n'existe plus."],
    [/not found/i, "Cet élément n'existe plus. La page s'est mise à jour."],
    [/name required/i, "Il faut un nom."],
    [/name and query required/i, "Il faut un nom et une requête."],
    [/query required/i, "Il faut une requête."],
  ];
  const missing = /^(Unknown cart|unknown category): (.+)$/i.exec(text);
  if (missing) {
    const what = /cart/i.test(missing[1]) ? "Le bac" : "La sélection";
    return `${what} « ${missing[2]} » n'existe plus : remplace-le là où il apparaît en rouge.`;
  }
  return known.find(([pattern]) => pattern.test(text))?.[1] ?? text;
}

/** A new heure type plays at once: a jingle, then titres from the rotation, when they exist. */
export function starterMotif(
  carts: { id: number; title: string; mode?: string }[],
  selections: { name: string }[],
): ClockPosition[] {
  const jingle = carts.find((cart) => /jingle/i.test(cart.title) && cart.mode !== "relay");
  const selection = selections.find((row) => /rotation/i.test(row.name)) ?? selections[0];
  const steps: ClockPosition[] = [];
  const base = { when: "sequential" as const, fallback_cart: null };
  if (jingle) steps.push({ ...base, kind: "jingle", cart: jingle.title, cart_id: jingle.id, category: null });
  if (selection) {
    steps.push({ ...base, kind: "musique", cart: null, cart_id: null, category: selection.name });
    return steps;
  }
  const programme =
    carts.find((cart) => /prog/i.test(cart.title) && cart.mode !== "relay") ??
    carts.find((cart) => cart.id !== jingle?.id && cart.mode !== "relay");
  if (programme) steps.push({ ...base, kind: "son", cart: programme.title, cart_id: programme.id, category: null });
  return steps;
}

const KIND_HINTS: Record<PositionKind, RegExp> = {
  jingle: /jingle|ident|virgule/i,
  son: /prog/i,
  pub: /pub|spot/i,
  musique: /rotation/i,
};

/** What a new step of this kind plays, until someone chooses: the bac or sélection its name suggests. */
export function defaultSource(
  kind: PositionKind,
  carts: { id: number; title: string; mode?: string }[],
  selections: { name: string }[],
): Pick<ClockPosition, "cart" | "cart_id" | "category"> {
  if (kind === "musique") {
    const selection = selections.find((row) => KIND_HINTS.musique.test(row.name)) ?? selections[0];
    return { cart: null, cart_id: null, category: selection?.name ?? null };
  }
  const playable = carts.filter((cart) => cart.mode !== "relay");
  const cart =
    playable.find((row) => KIND_HINTS[kind].test(row.title)) ??
    (kind === "son" ? playable.find((row) => !/jingle|pub|spot/i.test(row.title)) : undefined) ??
    null;
  return { cart: cart?.title ?? null, cart_id: cart?.id ?? null, category: null };
}
