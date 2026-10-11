/**
 * Dérivation des six piliers de santé antenne à partir de `/antenne/state.json`.
 * Pur : pas de React, testable en node.
 */
import type { AntenneIncident, AntenneListeners, AntenneState } from "./types";

export const ANTENNE_STATE_JSON = "/antenne/state.json";
export const ANTENNE_FLUSH_JSON = "/antenne/flush.json";

export type PillarTone = "ok" | "warn" | "alert" | "off";

export type Pillar = {
  key: "antenne" | "public" | "local" | "direct" | "moteur" | "alertes";
  label: string;
  value: string;
  tone: PillarTone;
  detail: string[];
};

export const SILENCE_WARN_S = 3;
export const SILENCE_ALERT_S = 20;

export type AirTone = "on" | "silence" | "direct" | "problem";

function airCause(input: {
  offline: boolean;
  silenceS: number | null;
  playoutReachable: boolean;
  incidentKinds: string[];
}): string {
  if (
    input.offline ||
    !input.playoutReachable ||
    input.incidentKinds.includes("playout_down")
  ) {
    return "Playout injoignable";
  }
  if (input.incidentKinds.includes("heartbeat")) return "Battement perdu";
  if (input.incidentKinds.includes("icecast_down")) return "Sortie Icecast coupée";
  const silence = input.silenceS ?? 0;
  if (silence >= SILENCE_WARN_S || input.incidentKinds.includes("silence")) {
    const seconds = Math.max(0, Math.round(silence));
    return seconds > 0 ? `Silence ${seconds} s` : "Silence";
  }
  return "";
}

/** Bandeau unique du pupitre. Même lecture pour tous les rôles. */
export function airBanner(input: {
  harbor: boolean;
  directTitle: string;
  offline: boolean;
  silenceS: number | null;
  playoutReachable: boolean;
  incidentKinds: string[];
}): { label: string; cause: string; tone: AirTone; hot: boolean } {
  if (input.harbor) {
    const name = input.directTitle.trim();
    return {
      label: name ? `Direct : ${name}` : "Direct",
      cause: "",
      tone: "direct",
      hot: false,
    };
  }
  const cause = airCause(input);
  const silence = input.silenceS ?? 0;
  if (cause.startsWith("Silence")) {
    return { label: cause, cause: "", tone: "silence", hot: silence >= SILENCE_ALERT_S };
  }
  if (cause) return { label: "Problème", cause, tone: "problem", hot: false };
  return { label: "En onde", cause: "", tone: "on", hot: false };
}
export const HEARTBEAT_OK_S = 2;
export const HEARTBEAT_WARN_S = 5;

const LOCAL_HOSTS = new Set(["icecast", "localhost", "127.0.0.1"]);

export function isLocalTarget(row: AntenneListeners): boolean {
  return LOCAL_HOSTS.has(row.host);
}

export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  const rest = m % 60;
  if (h < 24) return rest ? `${h} h ${String(rest).padStart(2, "0")}` : `${h} h`;
  const d = Math.floor(h / 24);
  return `${d} j ${h % 24} h`;
}

export function incidentLabel(incident: AntenneIncident): string {
  switch (incident.kind) {
    case "silence":
      return "Silence";
    case "playout_down":
      return "Playout injoignable";
    case "heartbeat":
      return "Battement perdu";
    case "icecast_down":
      return "Sortie Icecast";
    case "live_absent":
      return "Direct sans encodeur";
    default:
      return incident.kind;
  }
}

export function sourceLabelFr(source: string | undefined): string {
  switch ((source || "").toLowerCase()) {
    case "stream":
      return "Direct";
    case "relay":
      return "Relais";
    case "carts":
      return "Cart";
    case "jingles":
      return "Jingle";
    case "autodj":
      return "Auto-DJ";
    case "":
      return "—";
    default:
      return source as string;
  }
}

function listenersWord(n: number | null): string {
  if (n == null) return "auditeurs ?";
  return n === 1 ? "1 auditeur" : `${n} auditeurs`;
}

function outputPillar(
  key: "public" | "local",
  label: string,
  rows: AntenneListeners[],
  playoutReachable: boolean,
): Pillar {
  if (!rows.length) {
    return { key, label, value: "aucune sortie", tone: "off", detail: ["Pas de sortie Icecast déclarée."] };
  }
  const main = rows.find((row) => /\.mp3$/i.test(row.mount)) ?? rows[0];
  const detail = rows.map((row) => {
    const state = row.connected === false ? "déconnectée" : row.connected ? "connectée" : "état inconnu";
    const who = row.reachable ? (row.mounted ? listenersWord(row.listeners) : "mount absent") : "statut injoignable";
    return `${row.target} · ${state} · ${who}`;
  });
  if (!playoutReachable) {
    return { key, label, value: "playout ?", tone: "off", detail };
  }
  if (main.connected === false) {
    return { key, label, value: "coupée", tone: "alert", detail };
  }
  if (!main.reachable) {
    return { key, label, value: "connectée · statut ?", tone: "warn", detail };
  }
  if (!main.mounted) {
    return { key, label, value: "mount absent", tone: "warn", detail };
  }
  return { key, label, value: listenersWord(main.listeners), tone: "ok", detail };
}

export function derivePillars(state: AntenneState | null, harborOnAir: boolean): Pillar[] {
  if (!state) {
    const off = (key: Pillar["key"], label: string): Pillar => ({
      key,
      label,
      value: "—",
      tone: "off",
      detail: ["État antenne indisponible."],
    });
    return [
      off("antenne", "Antenne"),
      off("public", "Public"),
      off("local", "Local"),
      off("direct", "Direct"),
      off("moteur", "Moteur"),
      off("alertes", "Alertes"),
    ];
  }
  const { playout, engine, incidents, listeners } = state;

  // Antenne : silence et niveau
  let antenne: Pillar;
  if (!playout.reachable) {
    antenne = { key: "antenne", label: "Antenne", value: "playout ?", tone: "alert", detail: ["Liquidsoap /health injoignable."] };
  } else {
    const silence = playout.silence_s ?? 0;
    const level = playout.rms_db != null ? `${Math.round(playout.rms_db)} dB` : "niveau ?";
    const tone: PillarTone = silence >= SILENCE_ALERT_S ? "alert" : silence >= SILENCE_WARN_S ? "warn" : "ok";
    antenne = {
      key: "antenne",
      label: "Antenne",
      value: silence >= SILENCE_WARN_S ? `silence ${formatDuration(silence)}` : level,
      tone,
      detail: [
        `Source Liquidsoap : ${sourceLabelFr(playout.source)}`,
        `Niveau RMS : ${level}`,
        `Silence : ${silence.toFixed(1)} s`,
        playout.voiceover ? "Voix Hub : ducking actif" : "Voix Hub : off",
      ],
    };
  }

  const publicRows = listeners.filter((row) => !isLocalTarget(row));
  const localRows = listeners.filter(isLocalTarget);
  const publicPillar = outputPillar("public", "Public", publicRows, playout.reachable);
  const localPillar = outputPillar("local", "Local", localRows, playout.reachable);

  // Direct : harbor à l'antenne, sinon prochain créneau
  let direct: Pillar;
  if (harborOnAir || (playout.source || "").toLowerCase() === "stream") {
    const buffer = playout.harbor_s != null ? `tampon ${playout.harbor_s.toFixed(1)} s` : "tampon ?";
    direct = { key: "direct", label: "Direct", value: "à l’antenne", tone: "ok", detail: [`Harbor connecté · ${buffer}`] };
  } else if (state.next_live_slot) {
    const slot = state.next_live_slot;
    if (slot.active) {
      direct = {
        key: "direct",
        label: "Direct",
        value: `${slot.title} · encodeur absent`,
        tone: "warn",
        detail: [`Créneau ${slot.label} en cours, pas de harbor : l’horloge tient l’antenne (EF-01).`],
      };
    } else {
      direct = {
        key: "direct",
        label: "Direct",
        value: `${slot.title} dans ${formatDuration(slot.starts_in_s)}`,
        tone: "ok",
        detail: [`Prochain créneau live : ${slot.label}.`],
      };
    }
  } else {
    direct = { key: "direct", label: "Direct", value: "aucun prévu", tone: "off", detail: ["Aucun créneau live hebdo déclaré."] };
  }

  // Moteur
  const age = engine.heartbeat_age_s;
  let moteurTone: PillarTone = "ok";
  if (!engine.db_ok || age == null || age > HEARTBEAT_WARN_S) moteurTone = "alert";
  else if (age > HEARTBEAT_OK_S || !engine.playout_connected) moteurTone = "warn";
  const moteur: Pillar = {
    key: "moteur",
    label: "Moteur",
    value: age == null ? "pas de battement" : moteurTone === "ok" ? "OK" : `battement ${age.toFixed(1)} s`,
    tone: moteurTone,
    detail: [
      `Battement Liquidsoap : ${age == null ? "jamais" : `${age.toFixed(1)} s`}`,
      `Base : ${engine.db_ok ? "OK" : "KO"} · Playout : ${engine.playout_connected ? "connecté" : "déconnecté"}`,
      engine.tick_run_total != null
        ? `Ticks exécutés ${engine.tick_run_total} · évités ${engine.tick_gated_total ?? 0}`
        : "",
    ].filter(Boolean),
  };

  // Alertes
  const oldest = [...incidents].sort((a, b) => b.since_s - a.since_s)[0];
  const alertes: Pillar = {
    key: "alertes",
    label: "Alertes",
    value: incidents.length ? `${incidents.length} ouverte${incidents.length > 1 ? "s" : ""}` : "aucune",
    tone: incidents.length ? "alert" : "ok",
    detail: incidents.length
      ? incidents.map((i) => `${incidentLabel(i)} — ${i.detail} (depuis ${formatDuration(i.since_s)})`)
      : ["Aucun incident ouvert."],
  };
  if (oldest && oldest.kind === "live_absent" && incidents.length === 1) alertes.tone = "warn";

  return [antenne, publicPillar, localPillar, direct, moteur, alertes];
}

export function worstTone(pillars: Pillar[]): PillarTone {
  if (pillars.some((p) => p.tone === "alert")) return "alert";
  if (pillars.some((p) => p.tone === "warn")) return "warn";
  if (pillars.every((p) => p.tone === "off")) return "off";
  return "ok";
}
