/**
 * L'horloge du titre à l'antenne, entre deux battements du moteur : où il en est, et
 * ce qu'il lui reste. Pur : pas de React, testable en node.
 */
import type { LiveSnapshot } from "./types";

/** Le titre que l'horloge suit, calé sur un battement du moteur. */
export type ClockAnchor = {
  /** Le titre : l'heure où il est passé à l'antenne, son titre et son artiste. */
  key: string;
  /** L'heure de son début, en ms, d'après l'écoulé que dit le moteur. */
  atMs: number;
  /** Sa durée, en secondes. 0 tant que le moteur ne la dit pas. */
  duration: number;
};

export type ClockReading = {
  elapsedSec: number;
  remainingSec: number;
  /** 1 quand la durée n'est pas connue : l'avancée ne se montre pas. */
  durationSec: number;
};

/** Au-delà de cet écart, l'écoulé du moteur ne suit plus l'horloge : elle se recale sur lui. */
const RESYNC_S = 3;
/**
 * Au-delà de cet écart, la durée que dit le moteur remplace celle que l'horloge avait
 * retenue. En deçà, elle ne fait que trembler d'un battement à l'autre, et le compte à
 * rebours sauterait d'une seconde.
 */
const DURATION_DRIFT_S = 1.5;

/** Ce qui change quand un autre titre passe à l'antenne. */
export function liveTrackKey(live: LiveSnapshot | null | undefined): string {
  return `${live?.on_air ?? ""}|${live?.title ?? ""}|${live?.artist ?? ""}`;
}

/** La durée du titre d'après un battement : celle du moteur, sinon l'écoulé et le reste. 0 : inconnue. */
export function liveDuration(live: LiveSnapshot): number {
  const duration = Number(live.duration);
  if (Number.isFinite(duration) && duration > 0) return duration;
  const elapsed = Number(live.elapsed);
  const remaining = Number(live.remaining);
  if (!Number.isFinite(elapsed) || elapsed < 0) return 0;
  // Sans reste, le playout ne sait pas quand le titre finit : un relais, ou un titre qui démarre.
  return Number.isFinite(remaining) && remaining > 0 ? elapsed + remaining : 0;
}

/**
 * Cale l'horloge sur un battement du moteur. Elle garde son repère tant que le titre est
 * le même et que l'écoulé du moteur la suit. Sa durée, elle, suit chaque battement : le
 * premier d'un titre peut se tromper, le playout affinant son estimation ensuite. Retenue
 * une fois pour toutes, une durée fausse laissait l'avancée pleine jusqu'au titre suivant.
 */
export function anchorClock(
  previous: ClockAnchor | null,
  live: LiveSnapshot | null | undefined,
  wallMs: number,
): ClockAnchor | null {
  if (!live || live.status === "offline") return previous;
  const elapsed = Number(live.elapsed);
  if (!Number.isFinite(elapsed) || elapsed < 0) return previous;
  const key = liveTrackKey(live);
  const duration = liveDuration(live);
  const predicted = previous?.key === key ? (wallMs - previous.atMs) / 1000 : Number.NaN;
  if (!previous || previous.key !== key || Math.abs(predicted - elapsed) > RESYNC_S) {
    return { key, atMs: wallMs - elapsed * 1000, duration };
  }
  if (duration > 0 && Math.abs(duration - previous.duration) > DURATION_DRIFT_S) {
    return { ...previous, duration };
  }
  return previous;
}

/** Ce que l'horloge affiche à cet instant pour ce titre. Un autre titre que le sien : rien d'écoulé. */
export function readClock(anchor: ClockAnchor | null, key: string, wallMs: number): ClockReading {
  const own = anchor?.key === key ? anchor : null;
  const elapsedSec = own ? Math.round(Math.max(0, (wallMs - own.atMs) / 1000)) : 0;
  const durationSec = Math.max(1, Math.round(own ? own.duration : 1));
  return { elapsedSec, remainingSec: Math.max(0, durationSec - elapsedSec), durationSec };
}
