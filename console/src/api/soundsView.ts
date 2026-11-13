import { isHabillageCart } from "./cartFlags.ts";
import { LEGACY_ROTATION_FOLDER } from "./legacyLayout.ts";
import type { Cart } from "./types";

/** What a bac holds, as the Sons page shows it. */
export type BacKind = "fichiers" | "habillage" | "relais";
export type BacFilterId = "tous" | BacKind;

export const BAC_KINDS: { id: BacKind; label: string; plural: string }[] = [
  { id: "habillage", label: "Habillage", plural: "Habillage" },
  { id: "fichiers", label: "Fichiers", plural: "Fichiers" },
  { id: "relais", label: "Relais", plural: "Relais" },
];

export function bacKind(cart: Pick<Cart, "mode" | "bank_folder" | "bank_zone">): BacKind {
  if (cart.mode === "relay") return "relais";
  if (isHabillageCart(cart)) return "habillage";
  return "fichiers";
}

export function bacCounts(carts: Cart[]): Record<BacFilterId, number> {
  const counts: Record<BacFilterId, number> = { tous: carts.length, fichiers: 0, habillage: 0, relais: 0 };
  for (const cart of carts) counts[bacKind(cart)] += 1;
  // « Fichiers » lists every bac made of files, habillage included.
  counts.fichiers += counts.habillage;
  return counts;
}

/** Bacs grouped by kind, in reading order, without empty groups. */
export function groupBacs(carts: Cart[]): { kind: BacKind; label: string; carts: Cart[] }[] {
  return BAC_KINDS.map((kind) => ({
    kind: kind.id,
    label: kind.plural,
    carts: carts.filter((cart) => bacKind(cart) === kind.id),
  })).filter((group) => group.carts.length > 0);
}

export function cartTotalSeconds(cart: Pick<Cart, "sounds">): number {
  return cart.sounds.reduce((sum, sound) => sum + (sound.duration || 0), 0);
}

/** Running length of a track: 3:47, 1:02:30. */
export function formatClock(totalSec: number): string {
  const sec = Math.max(0, Math.round(totalSec || 0));
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** Length of a whole bac, short: 31 s, 52 min, 3 h 05. */
export function formatSpan(totalSec: number): string {
  const sec = Math.max(0, Math.round(totalSec || 0));
  if (sec < 60) return `${sec} s`;
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h === 0) return `${m} min`;
  return m === 0 ? `${h} h` : `${h} h ${String(m).padStart(2, "0")}`;
}

export function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value < 1024) return `${Math.max(0, Math.round(value || 0))} o`;
  const units = ["Ko", "Mo", "Go", "To"];
  let next = value / 1024;
  let index = 0;
  while (next >= 1024 && index < units.length - 1) {
    next /= 1024;
    index += 1;
  }
  const digits = next >= 10 ? 0 : 1;
  return `${next.toFixed(digits).replace(".", ",")} ${units[index]}`;
}

/** The station's quota, as the catalogue counts it: the inbox, the rotation and the collections. */
export type InboxQuota = { used: number; limit: number };
/** The disk under the bank, as df sees it. */
export type InboxDisk = { total: number; used: number; free: number };
/** What the Banque meter shows: the disk or the quota, whichever an upload meets first. */
export type BankRoom = { kind: "disque" | "quota"; used: number; total: number; free: number };

function isBytes(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

/**
 * The catalogue refuses a file bigger than the free disk, or one past the quota:
 * the meter shows whichever leaves less room. An older catalogue sends no disk.
 */
export function bankRoom(quota?: InboxQuota | null, disk?: InboxDisk | null): BankRoom | null {
  let room: BankRoom | null = null;
  if (quota && isBytes(quota.used) && isBytes(quota.limit) && quota.limit > 0) {
    room = { kind: "quota", used: quota.used, total: quota.limit, free: Math.max(0, quota.limit - quota.used) };
  }
  if (disk && isBytes(disk.total) && isBytes(disk.used) && isBytes(disk.free) && disk.total > 0) {
    if (!room || disk.free <= room.free) room = { kind: "disque", used: disk.used, total: disk.total, free: disk.free };
  }
  return room;
}

export function relayHost(url: string | null | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

export const MAX_DURATION_PRESETS = [
  { seconds: 1800, label: "30 min" },
  { seconds: 3600, label: "1 h" },
  { seconds: 7200, label: "2 h" },
  { seconds: 10800, label: "3 h" },
];

/** Formats the bank accepts, as the catalogue's tusd hook checks them. */
export const BANK_FORMATS = [".mp3", ".flac", ".ogg", ".opus", ".m4a", ".wav", ".aif", ".aiff"];

/**
 * The reason a tus upload failed, in the catalogue's words when it gave one.
 * tus-js-client wraps the hook's refusal: "… response code: 400, response text: quota dépassé, request id: …".
 */
export function tusReason(message: string | null | undefined): string {
  const text = (message || "").trim();
  const said = /response text: ([\s\S]*?)(?:, request id:|$)/.exec(text)?.[1]?.trim();
  if (said) return said;
  if (/response code: 413/.test(text)) return "fichier trop lourd";
  if (/response code: 401|response code: 403/.test(text)) return "session expirée";
  if (/Failed to fetch|NetworkError|network/i.test(text)) return "connexion coupée";
  return text ? "envoi interrompu" : "";
}

/** A cut connection is worth retrying; a refusal by the catalogue is not. */
export function tusRetryable(message: string | null | undefined): boolean {
  const text = (message || "").trim();
  if (/response text: ([\s\S]*?)(?:, request id:|$)/.exec(text)?.[1]?.trim()) return false;
  return !/response code: 4\d\d/.test(text);
}

/** Where an upload lands: rotation, or one collection. folder is its path in the bank, as the catalogue says. */
export type BankDestination = { id: string; label: string; group: "rotation" | "archives"; folder: string };

/** Until the catalogue answers, rotation is the only destination known for sure. */
export const ROTATION_DESTINATION: BankDestination = {
  id: "rotation",
  label: "Rotation",
  group: "rotation",
  folder: LEGACY_ROTATION_FOLDER,
};

export function destinationLabel(list: BankDestination[], id: string | null | undefined): string {
  return list.find((item) => item.id === id)?.label ?? (id || "");
}

function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("fr");
}

/** Banks whose name or folder holds every word typed, accents ignored. */
export function filterDestinations(list: BankDestination[], query: string): BankDestination[] {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (!words.length) return list;
  return list.filter((item) => {
    const text = fold(`${item.label} ${item.folder}`);
    return words.every((word) => text.includes(word));
  });
}

/** Same rule as the catalogue: lowercase, digits, dashes, 40 at most. */
export const BANK_FOLDER = /^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$/;

/** « Archives Jazz été 2024 » -> archives-jazz-ete-2024. */
export function bankFolderOf(label: string): string {
  return fold(label)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40)
    .replace(/-+$/, "");
}

export type BankProblem = { field: "label" | "folder"; message: string } | null;

/** Why a new bank cannot be created as typed, and which field to fix. */
export function bankProblem(list: BankDestination[], label: string, folder: string): BankProblem {
  const name = label.trim().replace(/\s+/g, " ");
  if (!name) return { field: "label", message: "Donne un nom à la collection." };
  if (name.length > 60) return { field: "label", message: "Nom trop long : 60 caractères au plus." };
  if (fold(name) === "rotation")
    return { field: "label", message: "« Rotation » est réservé à la musique de l'auto-DJ." };
  if (list.some((item) => fold(item.label) === fold(name))) {
    return { field: "label", message: "Une collection porte déjà ce nom." };
  }
  if (!BANK_FOLDER.test(folder)) {
    return { field: "folder", message: "Minuscules, chiffres et tirets, 40 caractères au plus." };
  }
  if (folder === "rotation") return { field: "folder", message: "« rotation » est réservé à la musique de l'auto-DJ." };
  const taken = list.find((item) => item.group === "archives" && item.id.toLowerCase() === folder);
  // Its path, as the catalogue says it: the console names no folder of the bank.
  if (taken) return { field: "folder", message: `${taken.folder} existe déjà.` };
  return null;
}

export function percentOf(done: number | undefined, total: number | undefined): number {
  if (!total || total <= 0 || !done) return 0;
  return Math.max(0, Math.min(100, Math.round((done / total) * 100)));
}

/** « il y a 3 min », « il y a 2 h », then the date. */
export function agoLabel(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "";
  const at = new Date(iso).getTime();
  if (Number.isNaN(at)) return "";
  const diff = Math.max(0, now - at);
  if (diff < 60_000) return "à l'instant";
  if (diff < 3_600_000) return `il y a ${Math.round(diff / 60_000)} min`;
  if (diff < 86_400_000) return `il y a ${Math.round(diff / 3_600_000)} h`;
  return new Date(at).toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
}
