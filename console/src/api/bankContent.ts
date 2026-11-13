import { displayNow } from "../lib/nowPlaying.ts";
import { agoLabel, formatBytes, type BankDestination } from "./soundsView.ts";

/** A file of rotation or of a collection, as the catalogue reads it on the disk. */
export type BankFile = {
  /** Its path below the folder of the collection: what the catalogue takes back. */
  name: string;
  title: string;
  artist: string;
  /** Null for a file that is not a sound. */
  duration: number | null;
  bytes: number;
  modified: string;
};

/** Rotation or a collection, with what it holds. */
export type BankShelf = BankDestination & { count: number; bytes: number };

export type BankPage = {
  destination: BankDestination;
  files: BankFile[];
  /** Every file of the collection. */
  total: number;
  /** Those the search keeps. */
  matched: number;
  bytes: number;
  /** The catalogue has not read every tag yet: the search may find more in a moment. */
  partial: boolean;
};

export type BankSort = "name" | "recent";
export type BankFailure = { name: string; reason: string };
/** What a removal or a move did. `stopped` says why it did not go to the end. */
export type BankChange = { done: string[]; failed: BankFailure[]; stopped: string };

/** One page of the list. */
export const BANK_PAGE = 100;
/** Titles sent by one request: a move to another disk copies, and nginx waits 30 s. */
export const BANK_BATCH = 25;

const READ_WAIT = 20_000;
const SEND_WAIT = 30_000;

/** The catalogue is older than this view: it does not know its routes. */
export class BankUnsupportedError extends Error {
  constructor() {
    super("Cette vue demande un catalogue plus récent. Mets à jour la station.");
  }
}

export class BankCallError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** A change sent, and no answer: it may have been made. */
export const MAYBE_DONE = "Pas de réponse du catalogue : le geste a peut-être été fait. Vérifie la liste avant de recommencer.";

/**
 * What to say of a refusal, from its status and the catalogue's own word.
 * Null: the catalogue does not know the route, it is older than the console.
 * `write`: a change was sent. nginx gives up after 30 s with a 504, or a 502
 * when the catalogue drops the request, while the change may go on or be half
 * done: the message says so.
 */
export function callProblem(status: number, said: string | undefined, write = false): string | null {
  const word = (said || "").trim();
  if (status === 404 && word === "not_found") return null;
  if (status === 401) return "Session expirée : recharge la page et reconnecte-toi.";
  if (status === 403 && word === "droit insuffisant") {
    return "Il faut le rôle Programmateur pour changer les titres de la banque.";
  }
  if (status === 403 && word === "réservé à un admin") return "Réservé à un admin.";
  // The catalogue answered itself, before changing anything: the engine did not answer it.
  if (status >= 500 && /automate/.test(word)) return "Le moteur ne répond pas au catalogue. Réessaie dans un instant.";
  if (status === 502 || status === 503 || status === 504) {
    return write ? MAYBE_DONE : "Le catalogue ne répond pas. Réessaie dans un instant.";
  }
  // The catalogue speaks French: its sentence says what to fix.
  if (word && word !== "not_found") return /[.!?]$/.test(word) ? word : `${word}.`;
  return "Le catalogue a refusé la demande.";
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(
      `/library${path}`,
      body === undefined
        ? { cache: "no-store", signal: AbortSignal.timeout(READ_WAIT) }
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(SEND_WAIT),
          },
    );
  } catch (caught) {
    const late = caught instanceof DOMException && caught.name === "TimeoutError";
    if (late && body !== undefined) throw new BankCallError(MAYBE_DONE, 0);
    throw new BankCallError("Le catalogue ne répond pas. Réessaie dans un instant.", 0);
  }
  const payload = (await response.json().catch(() => ({}))) as T & { error?: string };
  if (response.ok) return payload;
  const problem = callProblem(response.status, payload.error, body !== undefined);
  if (problem === null) throw new BankUnsupportedError();
  throw new BankCallError(problem, response.status);
}

export async function bankShelves(): Promise<BankShelf[]> {
  const payload = await call<{ destinations?: BankShelf[] }>("/collection/list.json");
  return Array.isArray(payload.destinations) ? payload.destinations : [];
}

export async function bankFiles(
  id: string,
  options: { q?: string; offset?: number; sort?: BankSort } = {},
): Promise<BankPage> {
  const search = new URLSearchParams({ id, limit: String(BANK_PAGE), offset: String(options.offset ?? 0) });
  if (options.q?.trim()) search.set("q", options.q.trim());
  if (options.sort === "recent") search.set("sort", "recent");
  const payload = await call<Partial<BankPage>>(`/collection/files.json?${search}`);
  const files = Array.isArray(payload.files) ? payload.files : [];
  return {
    destination: payload.destination ?? { id, label: id, group: "archives", folder: "" },
    files,
    total: payload.total ?? files.length,
    matched: payload.matched ?? files.length,
    bytes: payload.bytes ?? 0,
    partial: payload.partial === true,
  };
}

/** Where the browser reads a file of the bank, for a pre-listen. */
export function bankFileUrl(id: string, name: string): string {
  return `/library/collection/file?${new URLSearchParams({ id, name })}`;
}

export function chunks<T>(items: T[], size: number): T[][] {
  const parts: T[][] = [];
  for (let start = 0; start < items.length; start += size) parts.push(items.slice(start, start + size));
  return parts;
}

/** `left`: the titles the catalogue had no time for, before nginx gives up waiting. */
type BatchAnswer = { removed?: string[]; moved?: string[]; failed?: BankFailure[]; left?: string[] };

/**
 * Batch after batch. What the catalogue had no time for goes first in the next
 * one. A batch that gets no answer stops the rest, and says so.
 */
async function inBatches(
  names: string[],
  send: (batch: string[]) => Promise<BatchAnswer>,
  onProgress?: (done: number, total: number) => void,
): Promise<BankChange> {
  const change: BankChange = { done: [], failed: [], stopped: "" };
  let queue = [...names];
  while (queue.length) {
    const batch = queue.slice(0, BANK_BATCH);
    let answer: BatchAnswer;
    try {
      answer = await send(batch);
    } catch (caught) {
      if (caught instanceof BankUnsupportedError) throw caught;
      change.stopped = caught instanceof Error ? caught.message : "Le catalogue ne répond pas.";
      break;
    }
    const done = answer.removed ?? answer.moved ?? [];
    const failed = answer.failed ?? [];
    // Only names of this batch come back, and the catalogue always does its first one.
    const left = (answer.left ?? []).filter((name) => batch.includes(name));
    change.done.push(...done);
    change.failed.push(...failed);
    if (left.length >= batch.length) {
      change.stopped = "Le catalogue n'a rien pu faire de ces titres. Réessaie dans un instant.";
      break;
    }
    queue = [...left, ...queue.slice(batch.length)];
    onProgress?.(names.length - queue.length, names.length);
  }
  return change;
}

/** Send titles to the bank's trash. */
export function removeBankFiles(
  id: string,
  names: string[],
  onProgress?: (done: number, total: number) => void,
): Promise<BankChange> {
  return inBatches(names, (batch) => call<BatchAnswer>("/collection/remove.json", { id, names: batch }), onProgress);
}

/** Move titles to rotation or to another collection. */
export function moveBankFiles(
  id: string,
  to: string,
  names: string[],
  onProgress?: (done: number, total: number) => void,
): Promise<BankChange> {
  return inBatches(names, (batch) => call<BatchAnswer>("/collection/move.json", { id, to, names: batch }), onProgress);
}

export async function renameCollection(id: string, label: string): Promise<BankDestination> {
  const payload = await call<{ destination?: BankDestination }>("/collection/rename.json", { id, label });
  if (!payload.destination) throw new BankCallError("Le catalogue a refusé la demande.", 0);
  return payload.destination;
}

/** Deletes an empty collection. Returns how many hidden files went to the trash with it. */
export async function deleteCollection(id: string): Promise<number> {
  const payload = await call<{ deleted?: string; trashed?: number }>("/collection/delete.json", { id });
  return typeof payload.trashed === "number" ? payload.trashed : 0;
}

// The formats the engine plays: AUDIO_SUFFIXES, in engine/radiotomate/services/media_bank.py.
const AUDIO_NAMES = /\.(mp3|wav|wave|flac|ogg|oga|opus|m4a|aac|aiff|aif|wma|mp2|webm)$/i;

/** A sound, by its name. Anything else in a collection is a file left there, that nothing plays. */
export function isAudioName(name: string): boolean {
  return AUDIO_NAMES.test(name);
}

/** The subfolder a title sits in, below its collection: « » at its root. */
export function subfolderOf(name: string): string {
  const cut = name.lastIndexOf("/");
  return cut > 0 ? name.slice(0, cut) : "";
}

/** Artist and title of a file: its tags, or what its name says (« Artiste - Titre »). */
export function bankLabels(file: Pick<BankFile, "name" | "title" | "artist">): { artist: string; title: string } {
  const base = file.name.split("/").pop() || file.name;
  const parsed = displayNow({ title: file.title || base, artist: file.artist || "" });
  return { artist: parsed.artist, title: parsed.title || file.title || base };
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

export function titlesLabel(count: number): string {
  return count === 0 ? "Aucun titre" : plural(count, "titre", "titres");
}

/** « 12 titres · 1,2 Go », under the name of a collection. */
export function shelfFacts(shelf: Pick<BankShelf, "count" | "bytes">): string {
  return shelf.count ? `${titlesLabel(shelf.count)} · ${formatBytes(shelf.bytes)}` : "Vide";
}

/** « il y a 3 h », then the day; the year too once it is not this one. */
export function modifiedLabel(iso: string, now = Date.now()): string {
  const at = new Date(iso).getTime();
  if (Number.isNaN(at)) return "";
  if (now - at < 86_400_000 || new Date(at).getFullYear() === new Date(now).getFullYear()) return agoLabel(iso, now);
  return new Date(at).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });
}

/**
 * A click on a title's box. With Shift, everything between the last title clicked
 * and this one joins the selection, as in a bac.
 */
export function toggleSelection(
  order: string[],
  selected: ReadonlySet<string>,
  last: string | null,
  name: string,
  shift: boolean,
): Set<string> {
  const next = new Set(selected);
  if (shift && last != null) {
    const from = order.indexOf(last);
    const to = order.indexOf(name);
    if (from >= 0 && to >= 0) {
      for (let index = Math.min(from, to); index <= Math.max(from, to); index += 1) next.add(order[index]);
      return next;
    }
  }
  if (next.has(name)) next.delete(name);
  else next.add(name);
  return next;
}

/**
 * What a removal or a move did, and whether it is all done: one sentence per
 * part, each naming the collections it is about.
 */
export function changeSummary(
  kind: "removed" | "moved",
  change: BankChange,
  from: string,
  target = "",
): { text: string; tone: "success" | "error" } {
  const done = change.done.length;
  const failed = change.failed.length;
  const sentences: string[] = [];
  if (done && kind === "removed") {
    sentences.push(`${plural(done, "titre retiré", "titres retirés")} de « ${from} ».`);
  }
  if (done && kind === "moved") {
    sentences.push(`${plural(done, "titre déplacé", "titres déplacés")} de « ${from} » vers « ${target} ».`);
  }
  if (failed) {
    const reasons = [...new Set(change.failed.map((item) => item.reason))].slice(0, 2).join(", ");
    sentences.push(`${plural(failed, "titre refusé", "titres refusés")} : ${reasons}.`);
  }
  // Stopped before anything was done: the reason alone says it.
  if (change.stopped) sentences.push(sentences.length ? `Arrêt avant la fin. ${change.stopped}` : change.stopped);
  if (!sentences.length) sentences.push(`Rien n'a changé dans « ${from} ».`);
  return { text: sentences.join(" "), tone: failed || change.stopped ? "error" : "success" };
}

function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLocaleLowerCase("fr");
}

/** Why a collection cannot take this name, by the catalogue's own rules. */
export function renameProblem(list: BankDestination[], id: string, label: string): string {
  const name = label.trim().replace(/\s+/g, " ");
  if (!name) return "Donne un nom à la collection.";
  if (name.length > 60) return "Nom trop long : 60 caractères au plus.";
  if (fold(name) === "rotation") return "« Rotation » est réservé à la musique de l'auto-DJ.";
  if (list.some((item) => item.id !== id && fold(item.label) === fold(name))) return "Une collection porte déjà ce nom.";
  return "";
}
