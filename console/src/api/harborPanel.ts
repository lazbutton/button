import type { Emission, LiveSnapshot } from "./types";

function harborSource(source: string | undefined): boolean {
  const text = (source || "").toLowerCase();
  return text.includes("stream") || text.includes("harbor");
}

export type HarborPhase = "connected" | "waiting" | "absent";

export const HARBOR_PHASE_LABEL: Record<HarborPhase, string> = {
  connected: "Branché",
  waiting: "En attente",
  absent: "Absent",
};

export function harborPhase(input: {
  live: LiveSnapshot | null;
  playoutSource?: string;
  slotActive?: boolean;
  liveAbsent?: boolean;
}): HarborPhase {
  const live = input.live;
  const liveOn = live != null && live.status !== "offline";
  const connected = liveOn && (harborSource(live.source) || harborSource(input.playoutSource));
  if (connected) return "connected";
  if (live?.emission?.state === "waiting" || input.slotActive || input.liveAbsent) return "waiting";
  return "absent";
}

export function harborDetail(phase: HarborPhase, offline: boolean): string {
  if (offline && phase !== "connected") return "L’antenne ne répond pas.";
  if (phase === "connected") {
    return "L’encodeur est à l’antenne. Couper BUTT ou Mixxx rend la grille : le moteur vide les files.";
  }
  if (phase === "waiting") {
    return "Un créneau est ouvert, l’encodeur n’est pas là. L’horloge tient l’antenne.";
  }
  return "Pas d’encodeur branché. La rotation continue.";
}

export function weeklyHost(emissions: Emission[] | undefined, currentId: number | undefined): string {
  if (currentId == null) return "";
  const row = emissions?.find((item) => item.id === currentId && item.scope === "weekly");
  return (row?.host_username || "").trim();
}

export function slotRule(host: string, showTitle?: string): string {
  const name = host.trim();
  if (name) {
    const title = showTitle?.trim();
    const where = title ? ` « ${title} »` : "";
    return `Le créneau${where} est nommé ${name}. Seul ce compte, ou un admin, peut se brancher.`;
  }
  return "Si une émission nomme un identifiant, seul ce compte ou un admin passe sur ce créneau. Sinon, tout compte avec le droit Stream peut se brancher.";
}
