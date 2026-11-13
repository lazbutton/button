/**
 * Les règles des messages de la console, ceux qui s'affichent en bas à droite
 * de l'écran (`ui/AppToast.tsx`) : leur ton, et le temps qu'ils restent.
 */

/**
 * Le ton d'un message. Celui qui l'affiche le donne toujours : deviné d'après
 * le texte, un refus du moteur passait pour une confirmation.
 *
 * - `success` : c'est fait ;
 * - `error` : ce n'est pas fait, ou pas en entier ;
 * - `info` : à savoir, sans rien de fait ni de raté.
 */
export type ToastTone = "success" | "error" | "info";

/** Ce qu'un lecteur d'écran dit du ton, avant le texte : la couleur et l'icône ne lui parlent pas. */
export const TONE_LABEL: Record<ToastTone, string> = {
  success: "Succès",
  error: "Erreur",
  info: "Information",
};

/** Le temps de remarquer un message, avant de le lire. */
const NOTICE_MS = 2000;
/** La lecture, mot par mot, au rythme de quelqu'un qui fait autre chose en même temps. */
const WORD_MS = 350;
const SHORTEST_MS = 4000;
/** Un échec, ou un message qui porte un bouton comme « Annuler », reste au moins ce temps. */
const SHORTEST_KEPT_MS = 8000;
const LONGEST_MS = 20_000;

/**
 * Combien de temps un message reste à l'écran, en millisecondes : le temps de le
 * remarquer, puis de le lire. Un échec reste une fois et demie plus longtemps,
 * et personne ne règle ce temps à la main.
 */
export function toastDuration(text: string, tone: ToastTone, withAction = false): number {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  const reading = NOTICE_MS + words * WORD_MS;
  const floor = tone === "error" || withAction ? SHORTEST_KEPT_MS : SHORTEST_MS;
  return Math.min(LONGEST_MS, Math.max(floor, tone === "error" ? reading * 1.5 : reading));
}

/**
 * Le compte à rebours d'un message : ce qu'il lui restait quand il est parti ou
 * reparti, et depuis quand il court (`null` : en pause).
 */
export type ToastClock = { left: number; since: number | null };

/** Après une pause, un message reste au moins ce temps : il ne part pas sous le pointeur qui le quitte. */
export const RESUME_FLOOR_MS = 2000;

/** Un message qui s'affiche, onglet caché ou pointeur déjà dessus, attend d'être vu pour compter. */
export function startClock(duration: number, now: number, paused = false): ToastClock {
  return { left: duration, since: paused ? null : now };
}

/** Ce qu'il reste au compte à rebours à l'instant `now`. */
export function clockLeft(clock: ToastClock, now: number): number {
  return clock.since == null ? clock.left : Math.max(0, clock.left - (now - clock.since));
}

/** Le pointeur est sur le message, le clavier dedans, ou l'onglet caché : le temps ne passe plus. */
export function pauseClock(clock: ToastClock, now: number): ToastClock {
  return clock.since == null ? clock : { left: clockLeft(clock, now), since: null };
}

export function resumeClock(clock: ToastClock, now: number): ToastClock {
  return clock.since == null ? { left: Math.max(RESUME_FLOOR_MS, clock.left), since: now } : clock;
}
