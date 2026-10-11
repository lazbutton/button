import { fuzzyTitleMatch } from "./fuzzyTitle";
import type { Cart, CartMode, ScheduleMode } from "./types";

export const MODE_LABELS: Record<CartMode, string> = {
  playlist: "Une fois",
  playlist_loop: "Boucle",
  random: "Aléatoire",
  relay: "Relais",
};

export const MODE_HELP: Record<CartMode, string> = {
  playlist: "Joue les sons dans l’ordre, une fois.",
  playlist_loop: "Reprend au début après le dernier son.",
  random: "Tire un son au hasard parmi les pistes actives analysées.",
  relay: "Diffuse un flux Icecast externe. La durée max. est obligatoire.",
};

export const QUEUE_HELP = "Carts : file dédiée. Auto-DJ : le cart tourne dans l’horloge (Jingles ou Prog).";

export const URL_HELP = "Adresse HTTP du flux à relayer.";

export const MAX_DURATION_HELP = "Vide = illimité. Obligatoire en relais.";

export { identCart, isHabillageCart, relayUrlOk } from "./cartFlags";

export const SCHEDULE_HELP: Record<ScheduleMode, string> = {
  clock: "Joué par les horloges (positions, ancres) et les pads : aucun cron.",
  timed: "À une heure pile, hors rotation de l’heure en cours.",
  jingles: "Joue un son selon la minute et la seconde (ex. chaque heure).",
};

export const CRON_HELP = "* = toutes les valeurs (formule type crontab).";

export const WEEKDAYS = [
  { value: "0", label: "Lundi" },
  { value: "1", label: "Mardi" },
  { value: "2", label: "Mercredi" },
  { value: "3", label: "Jeudi" },
  { value: "4", label: "Vendredi" },
  { value: "5", label: "Samedi" },
  { value: "6", label: "Dimanche" },
] as const;

export type CartFilter = "all" | CartMode | "jingles";

export function cartMatches(cart: Cart, query: string, filter: CartFilter): boolean {
  if (query.trim() && !fuzzyTitleMatch(cart.title, query)) return false;
  if (filter === "all") return true;
  if (filter === "jingles") return cart.schedule_mode === "jingles";
  return cart.mode === filter;
}

export function splitDuration(total: number | null): { minutes: string; seconds: string } {
  if (!total) return { minutes: "", seconds: "" };
  return {
    minutes: String(Math.floor(total / 60)),
    seconds: String(total % 60),
  };
}

export function joinDuration(minutes: string, seconds: string): number | null {
  const m = Number(minutes || 0);
  const s = Number(seconds || 0);
  if (!Number.isFinite(m) || !Number.isFinite(s) || (m <= 0 && s <= 0)) return null;
  return m * 60 + s;
}

export function scheduleModeLabel(mode: ScheduleMode): string {
  if (mode === "jingles") return "Jingles";
  return mode === "clock" ? "Horloge" : "Horaire";
}

export function splitSoundTitle(raw: string): { artist: string; title: string } {
  const text = stripAudioExt(raw.trim().replace(/^\d+\s+/, ""));
  const cut = text.indexOf(" - ");
  if (cut > 0) {
    const artist = stripAudioExt(text.slice(0, cut).trim());
    let title = stripAudioExt(text.slice(cut + 3).trim().replace(/^\d+\s+/, ""));
    if (artist && title.toLowerCase().startsWith(artist.toLowerCase() + " - ")) {
      title = stripAudioExt(title.slice(artist.length + 3).trim().replace(/^\d+\s+/, ""));
    }
    if (artist && title) return { artist, title };
  }
  return { artist: "", title: text };
}

const AUDIO_EXT = /\.(mp3|flac|ogg|opus|oga|wav|m4a|aac|aiff|aif|wma)$/i;

function stripAudioExt(value: string): string {
  return value.replace(AUDIO_EXT, "").trim();
}

export function lastPlayedLabel(iso: string | null, at = Date.now()): string {
  if (!iso) return "Jamais";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Jamais";
  const diff = at - date.getTime();
  if (diff < 45_000) return "À l’instant";
  if (diff < 3_600_000) return `${Math.max(1, Math.round(diff / 60_000))} min`;
  const today = new Date(at).toDateString() === date.toDateString();
  if (today || diff < 86_400_000) {
    return date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString("fr-FR", { day: "2-digit", month: "short" });
}
