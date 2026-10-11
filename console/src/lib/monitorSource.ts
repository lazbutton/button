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
    if (raw === "nasgul" || raw === "lan") return "public";
    if (raw === "public" || raw === "files") return raw;
  } catch {
    /* proto */
  }
  return null;
}

export async function streamReachable(url: string, timeoutMs = 400): Promise<boolean> {
  if (!url) return false;
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      cache: "no-store",
      mode: "cors",
      signal: ctrl.signal,
    });
    if (!response.ok) return false;
    void response.body?.cancel();
    return true;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timer);
  }
}

export function writeMonitorSourceId(id: MonitorSourceId): void {
  try {
    window.localStorage.setItem(MONITOR_SOURCE_KEY, id);
  } catch {
    /* proto */
  }
}

/** Si le casque WAV n’existe pas, même hôte, mount MP3 public. */
export function fallbackMp3Stream(streamUrl: string): string {
  try {
    const next = new URL(streamUrl);
    if (next.pathname.endsWith(".wav")) next.pathname = "/button.mp3";
    next.search = "";
    next.hash = "";
    return next.toString();
  } catch {
    return streamUrl;
  }
}

export function monitorSources(brand: Brand): MonitorSource[] {
  const publicStream =
    brand.apps.player?.productionStreamUrl ||
    brand.apps.player?.streamUrl ||
    "https://radio.lazbutton.xyz/button.mp3";
  const publicStatus =
    brand.apps.player?.icecastStatusUrl ||
    "https://radio.lazbutton.xyz/status-json.xsl";
  const publicNow = "https://radio.lazbutton.xyz/now.json";

  const sources: MonitorSource[] = [
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
      label: "Conducteur (fichiers)",
      chip: "Fichiers",
      hint: "MP3 du conducteur, collés à l’horloge. Ancre dure = coupe. Live plateau → l’antenne.",
      stream: publicStream,
      nowUrl: publicNow,
      statusUrl: publicStatus,
    },
  ];
  return sources.filter((source) => Boolean(source.stream));
}

export function sourceById(
  sources: MonitorSource[],
  id: MonitorSourceId,
): MonitorSource {
  return (
    sources.find((source) => source.id === id) ||
    sources.find((source) => source.id === "public") ||
    sources[0]
  );
}
