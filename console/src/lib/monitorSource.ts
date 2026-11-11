import type { Brand } from "./brand";

export type MonitorSourceId = "public" | "files";

export type MonitorSource = {
  id: MonitorSourceId;
  label: string;
  chip: string;
  hint: string;
  stream: string;
  nowUrl: string;
  statusUrl: string;
};

export const MONITOR_SOURCE_KEY = "button-monitor-source";

export function readMonitorSourceId(): MonitorSourceId | null {
  try {
    const raw = window.localStorage.getItem(MONITOR_SOURCE_KEY);
    if (raw === "public" || raw === "files") return raw;
  } catch {
    /* proto */
  }
  return null;
}

export function writeMonitorSourceId(id: MonitorSourceId): void {
  try {
    window.localStorage.setItem(MONITOR_SOURCE_KEY, id);
  } catch {
    /* proto */
  }
}

/**
 * Les sources du casque, lues dans les réglages de la station, posés sur brand.json
 * (`withStation`). Sans flux public réglé, aucune : le casque n'a rien à écouter, et son
 * bouton dit quoi régler. Pas d'adresse en repli : ADR 0007.
 */
export function monitorSources(brand: Brand): MonitorSource[] {
  const player = brand.apps?.player;
  const publicStream = player?.productionStreamUrl || player?.streamUrl || "";
  if (!publicStream) return [];
  const publicStatus = player?.icecastStatusUrl || "";
  const publicNow = player?.productionNowUrl || "";

  return [
    {
      id: "public",
      label: "Antenne publique",
      chip: "Antenne",
      hint: "Ce que l’auditeur entend.",
      stream: publicStream,
      nowUrl: publicNow,
      statusUrl: publicStatus,
    },
    {
      id: "files",
      // Commence par la pastille du casque, « Fichiers » : le nom du bouton reprend ce qu'il affiche.
      label: "Fichiers du conducteur",
      chip: "Fichiers",
      hint: "MP3 du conducteur, collés à l’horloge. Ancre dure = coupe. Live plateau → l’antenne.",
      stream: publicStream,
      nowUrl: publicNow,
      statusUrl: publicStatus,
    },
  ];
}

/** La source choisie, sinon l'antenne publique. Sans flux réglé, aucune. */
export function sourceById(
  sources: MonitorSource[],
  id: MonitorSourceId,
): MonitorSource | undefined {
  return (
    sources.find((source) => source.id === id) ||
    sources.find((source) => source.id === "public") ||
    sources[0]
  );
}
