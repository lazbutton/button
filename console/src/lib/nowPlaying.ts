export type NowPlaying = {
  title: string;
  artist: string;
  duration: number | null;
  startedAt: number | null;
};

type NowPayload = {
  title?: string;
  artist?: string;
  album?: string;
  duration?: number | string;
  started_at?: string;
  on_air?: string;
  received_at?: string;
  remaining?: number | string;
  server_description?: string;
  server_name?: string;
};

type IcecastStatus = {
  icestats?: {
    source?: NowPayload | NowPayload[];
  };
};

const AUDIO_EXT = /\.(mp3|flac|ogg|opus|oga|wav|m4a|aac|aiff|aif|wma)$/i;
const LEADING_INDEX = /^\d+\s*[-.]?\s+/;

function parseSec(value: number | string | undefined): number | null {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function parseTime(value: string | undefined): number | null {
  if (!value) return null;
  const t = Date.parse(value);
  return Number.isFinite(t) ? t : null;
}

function looksLikeMediaFile(raw: string): boolean {
  const text = raw.trim();
  if (!text) return false;
  return AUDIO_EXT.test(text) || text.includes("/") || text.includes("\\");
}

/** Enlève chemin, extension audio, index de piste. */
export function stripMediaName(raw: string): string {
  let text = raw.trim();
  if (!text) return "";
  const slash = Math.max(text.lastIndexOf("/"), text.lastIndexOf("\\"));
  if (slash >= 0) text = text.slice(slash + 1);
  text = text.replace(AUDIO_EXT, "");
  text = text.replace(/_/g, " ").replace(/\s+/g, " ").trim();
  return text.replace(LEADING_INDEX, "").trim();
}

/** « NightFever » → « Night Fever », « et » / « avec » collés aussi. */
export function humanizeName(raw: string): string {
  let text = raw.replace(/_+/g, " ").replace(/\s+/g, " ").trim();
  text = text.replace(/([a-zà-ÿ])(et|avec|and|feat|ft)(?=[A-Z])/g, "$1 $2 ");
  text = text.replace(/([A-ZÀ-Ý]+)([A-ZÀ-Ý][a-zà-ÿ])/g, "$1 $2");
  text = text.replace(/([a-zà-ÿ])([A-ZÀ-Ý])/g, "$1 $2");
  return text.replace(/\s+/g, " ").trim();
}

function splitArtistTitle(raw: string): { artist: string; title: string } | null {
  const text = stripMediaName(raw);
  const sep = text.includes(" — ") ? " — " : text.includes(" - ") ? " - " : null;
  if (!sep) return null;
  const cut = text.indexOf(sep);
  const artist = text.slice(0, cut).trim();
  let title = text.slice(cut + sep.length).trim().replace(LEADING_INDEX, "").trim();
  if (artist && title.toLowerCase().startsWith(artist.toLowerCase() + sep)) {
    title = title.slice(artist.length + sep.length).trim();
  }
  if (artist && title) return { artist, title };
  return null;
}

/** « Artiste-Titre » sans espaces. Pas « L-O-V-E ». */
function splitCompactHyphen(raw: string): { artist: string; title: string } | null {
  const text = stripMediaName(raw);
  if (!text || text.includes(" - ") || text.includes(" — ")) return null;
  if (/^(?:[A-Za-z0-9]-){2,}[A-Za-z0-9]$/.test(text)) return null;
  const cut = text.indexOf("-");
  if (cut < 2) return null;
  const artist = text.slice(0, cut).trim();
  const title = text.slice(cut + 1).trim();
  if (artist.length < 2 || title.length < 2) return null;
  return { artist, title };
}

/**
 * Icecast / now.json envoient souvent le nom de fichier.
 * Cart Radiotomate : artist = nom de playlist, title = « Artiste - Titre ».
 */
export function displayNow(data: NowPayload): NowPlaying {
  const rawTitle = (data.title || "").trim();
  const rawArtist = (data.artist || "").trim();
  const album = (data.album || "").trim();
  const server = (data.server_name || "").trim();

  const fileTitle = looksLikeMediaFile(rawTitle);
  let title = fileTitle ? stripMediaName(rawTitle) : rawTitle;
  let artist = looksLikeMediaFile(rawArtist) ? stripMediaName(rawArtist) : rawArtist;
  if (artist && server && artist.toLowerCase() === server.toLowerCase()) {
    artist = "";
  }
  // Radiotomate met le nom du bac dans artist tant que le titre est le fichier.
  if (fileTitle) artist = "";

  const combined = fileTitle
    ? splitArtistTitle(title) ?? splitCompactHyphen(title)
    : !artist || (album && artist === album)
      ? splitArtistTitle(title)
      : null;
  if (combined) {
    artist = humanizeName(combined.artist);
    title = humanizeName(combined.title);
  } else {
    title = humanizeName(title);
    if (artist) artist = humanizeName(artist);
  }
  if (album && artist === album) artist = "";

  const duration = parseSec(data.duration);
  const startedAt =
    parseTime(data.started_at) ||
    parseTime(data.on_air) ||
    (duration && parseSec(data.remaining)
      ? Date.now() - (duration - (parseSec(data.remaining) as number)) * 1000
      : parseTime(data.received_at));
  return { title, artist, duration, startedAt: duration ? startedAt : null };
}

export function remainingSeconds(now: NowPlaying, at = Date.now()): number | null {
  if (!now.duration || !now.startedAt) return null;
  return Math.max(0, now.duration - (at - now.startedAt) / 1000);
}

export function formatRemain(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `−${m}:${r.toString().padStart(2, "0")}`;
}

const NOW_URL = "https://radio.lazbutton.xyz/now.json";
const ICECAST_STATUS_URL = "https://radio.lazbutton.xyz/status-json.xsl";

export async function fetchNowPlaying(
  nowUrl = NOW_URL,
  statusUrl = ICECAST_STATUS_URL,
): Promise<NowPlaying | null> {
  if (nowUrl) {
    try {
      const res = await fetch(nowUrl, { cache: "no-store" });
      if (res.ok) return displayNow((await res.json()) as NowPayload);
    } catch {
      /* Icecast fallback */
    }
  }
  if (!statusUrl) return null;
  try {
    const res = await fetch(statusUrl, { cache: "no-store" });
    if (!res.ok) return null;
    const json = (await res.json()) as IcecastStatus;
    const src = json.icestats?.source;
    const first = Array.isArray(src) ? src[0] : src;
    return first ? displayNow(first) : null;
  } catch {
    return null;
  }
}
