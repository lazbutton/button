/**
 * Ce que dit la barre du haut : état de l'antenne, auditeurs, santé, casque.
 * Pur : pas de React, testable en node.
 */
import { formatRemain } from "../lib/nowPlaying.ts";
import {
  airBanner,
  derivePillars,
  isLocalTarget,
  worstTone,
  type Pillar,
  type PillarTone,
} from "./antenneState.ts";
import { isHarborSource } from "./rundownLive.ts";
import type { AntenneState, LiveSnapshot } from "./types";

export type TopAirTone = "on" | "direct" | "warn" | "alert" | "off";

export type TopAir = {
  tone: TopAirTone;
  /** En onde, Direct, Silence 12 s, Playout injoignable… */
  label: string;
  /** Ce qui tient l'antenne (Auto-DJ, Relais…) ou le nom du direct. */
  detail: string;
};

/** Au-delà, l'état antenne affiché n'est plus celui du moment. */
export const STATE_STALE_S = 20;

export function liveSourceLabel(live: LiveSnapshot | null): { label: string; color: "gray" | "green" | "red" } {
  if (!live || live.status === "offline") return { label: "Arrêt", color: "gray" };
  const raw = (live.source || "").trim().toLowerCase();
  if (/live|harbor|stream/.test(raw)) return { label: "Direct", color: "red" };
  if (raw.includes("jingle")) return { label: "Jingles", color: "green" };
  if (raw.includes("cart")) return { label: "Carts", color: "green" };
  if (raw.includes("relay") || raw.includes("relais")) return { label: "Relais", color: "green" };
  return { label: "Auto-DJ", color: "green" };
}

/** Ce qui tient l'antenne, dit pareil dans la barre et sur le pupitre. */
export function airSourceLabel(live: LiveSnapshot): string {
  const show = live.emission;
  if (show && show.scope === "dated" && show.kind === "set" && show.state === "on_air") {
    return "Émission datée";
  }
  return liveSourceLabel(live).label;
}

/** Même lecture que le bandeau du pupitre, en plus court. */
export function topAir(input: {
  live: LiveSnapshot | null;
  antenne: AntenneState | null;
  loading: boolean;
  unreachable: boolean;
}): TopAir {
  const { live, antenne } = input;
  // Le dernier relevé ne vaut plus rien quand l'automate ne répond plus.
  if (input.unreachable) return { tone: "alert", label: "Automate injoignable", detail: "" };
  if (!live && input.loading) return { tone: "off", label: "Connexion…", detail: "" };
  const offline = !live || live.status === "offline";
  const harbor = !offline && isHarborSource(live?.source);
  const banner = airBanner({
    harbor,
    directTitle: live?.emission?.title ?? "",
    offline,
    silenceS: antenne?.playout.silence_s ?? null,
    playoutReachable: antenne ? antenne.playout.reachable : !offline,
    incidentKinds: (antenne?.incidents ?? []).map((incident) => incident.kind),
  });
  if (banner.tone === "direct") {
    return { tone: "direct", label: "Direct", detail: live?.emission?.title?.trim() ?? "" };
  }
  if (banner.tone === "silence") {
    return { tone: banner.hot ? "alert" : "warn", label: banner.label, detail: "" };
  }
  if (banner.tone === "problem") {
    return { tone: "alert", label: banner.cause || "Problème", detail: "" };
  }
  return { tone: "on", label: "En onde", detail: live ? airSourceLabel(live) : "" };
}

/** Auditeurs du flux public : mounts hors studio, sinon mounts locaux. Le casque .wav ne compte pas. */
export function audience(state: AntenneState | null): number | null {
  if (!state) return null;
  const rows = state.listeners.filter(
    (row) => row.reachable && row.mounted && row.listeners != null && !/\.wav$/i.test(row.mount),
  );
  if (!rows.length) return null;
  const outside = rows.filter((row) => !isLocalTarget(row));
  return (outside.length ? outside : rows).reduce((sum, row) => sum + (row.listeners ?? 0), 0);
}

export function audienceLabel(count: number): string {
  return count === 1 ? "1 auditeur" : `${count} auditeurs`;
}

const PARIS_WALL = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Europe/Paris",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

function wallMs(text: string): number {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/.exec(text);
  if (!match) return Number.NaN;
  const [, y, mo, d, h, mi, s] = match.map(Number);
  return Date.UTC(y, mo - 1, d, h, mi, s);
}

function parisWallMs(now: Date): number {
  const parts = PARIS_WALL.formatToParts(now);
  const get = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((part) => part.type === type)?.value);
  return Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"), get("second"));
}

/** `at` est une heure murale de Paris (TZ du conteneur), pas celle du navigateur. */
export function stateAgeS(at: string, now: Date): number | null {
  const wall = wallMs(at);
  if (!Number.isFinite(wall)) return null;
  return (parisWallMs(now) - wall) / 1000;
}

export type TopHealth = {
  tone: PillarTone;
  pillars: Pillar[];
  /** Incidents ouverts. */
  open: number;
  stale: boolean;
};

export function topHealth(state: AntenneState | null, live: LiveSnapshot | null, now: Date): TopHealth {
  const age = state ? stateAgeS(state.at, now) : null;
  const stale = age == null || age > STATE_STALE_S;
  const harbor = Boolean(live && live.status !== "offline" && isHarborSource(live.source));
  const pillars = derivePillars(stale ? null : state, harbor);
  return {
    tone: worstTone(pillars),
    pillars,
    open: stale ? 0 : state?.incidents.length ?? 0,
    stale,
  };
}

/** Initiales du compte pour l'avatar : « atelier » → « AT », « jean-luc m » → « JM ». */
export function initials(username: string): string {
  const words = username
    .trim()
    .split(/[\s._-]+/)
    .filter(Boolean);
  if (!words.length) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return `${words[0][0]}${words[words.length - 1][0]}`.toUpperCase();
}

export type ListenState = {
  muted: boolean;
  kind: "icecast" | "files" | "harbor";
  fileMissing: boolean;
  fileLoading: boolean;
  /** Flux : la dernière connexion a échoué, le casque réessaie seul. */
  streamDown: boolean;
  /** Fichiers : secondes avant que l'horloge lance le titre. */
  startsInS: number | null;
  lagMs: number | null;
};

/** Infobulle du bouton casque. */
export function listenHint(state: ListenState, source: string): string {
  if (state.muted) return `Écouter au casque : ${source}`;
  if (state.fileMissing) return "Fichier du conducteur introuvable";
  if (state.streamDown) return "Le flux ne répond pas : le casque réessaie seul";
  if (state.kind === "harbor") return "Direct plateau : le casque suit l'antenne";
  if (state.kind === "files") {
    if (state.fileLoading) return "Décodage du fichier…";
    if (state.startsInS != null && state.startsInS > 0) {
      return `Le titre démarre dans ${formatRemain(state.startsInS).slice(1)}`;
    }
    if (state.lagMs != null) return `Écart avec l'horloge : ${Math.abs(state.lagMs)} ms`;
    return "Conducteur, calé sur l'horloge";
  }
  if (state.lagMs != null) return `Retard du casque : ${Math.max(0, state.lagMs)} ms`;
  return "Couper le casque";
}
