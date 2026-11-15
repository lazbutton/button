import type { BankTitle } from "./bankTitles.ts";
import type { Decided, FicheProposition } from "./fiches.ts";
import { FIELD_LABELS, fieldValue } from "./fiches.ts";

/**
 * Les arrivées de la banque (FON-81) : les titres indexés depuis 30 jours, comme
 * le moteur les rend (`GET /media/arrivals.json`). « Ranger » accepte les
 * propositions sûres (FON-27), puis renomme d'après la fiche (FON-68).
 */

export type ArrivalTwin = Pick<BankTitle, "id" | "title" | "artist" | "duration" | "zone" | "collection" | "path">;

export type Arrival = BankTitle & {
  /** À l'heure de Paris. */
  added: string | null;
  /** La recherche en ligne l'a déjà cherché (FON-25). */
  searched: boolean;
  status: string;
  level: string;
  /** Ses propositions encore à décider. */
  propositions: FicheProposition[];
  /** Les propositions sûres, que « Ranger » accepte. */
  sure: number[];
  /** Une proposition attend une personne : le titre s'ouvre. */
  review: boolean;
  /** Le nom qu'il prendra, une fois ses propositions sûres acceptées ; null s'il garde le sien. */
  to: string | null;
  ready: boolean;
  duplicates: ArrivalTwin[];
};

export type Arrivals = {
  days: number;
  model: string;
  total: number;
  ready: number;
  review: number;
  waiting: number;
  duplicates: number;
  titles: Arrival[];
};

export function arrivalsPath(model: string): string {
  return `/media/arrivals.json?${new URLSearchParams({ model }).toString()}`;
}

function counted(value: number, one: string, many: string): string {
  return `${value.toLocaleString("fr-FR")} ${value === 1 ? one : many}`;
}

/** « 12 titres arrivés en 30 jours », puis ce qui attend. */
export function arrivalsLine(payload: Arrivals): string {
  if (!payload.total) return `Aucun titre arrivé en ${payload.days} jours.`;
  const parts = [`${counted(payload.total, "titre arrivé", "titres arrivés")} en ${payload.days} jours`];
  if (payload.ready) parts.push(`${counted(payload.ready, "prêt", "prêts")} à ranger`);
  if (payload.review) parts.push(`${counted(payload.review, "à relire", "à relire")}`);
  if (payload.waiting) parts.push(`${counted(payload.waiting, "pas encore cherché", "pas encore cherchés")}`);
  return `${parts.join(", ")}.`;
}

/** Ce que « Ranger » fait d'un lot : les propositions sûres acceptées, les fichiers renommés. */
export function tidyLot(titles: Arrival[]): {
  propositions: number[];
  renamed: number[];
  titles: number;
} {
  const ready = titles.filter((title) => title.ready);
  return {
    propositions: ready.flatMap((title) => title.sure),
    renamed: ready.filter((title) => title.to).map((title) => title.id),
    titles: ready.length,
  };
}

export function tidyAllAction(count: number): string {
  return count === 1 ? "Ranger le titre sûr" : `Ranger les ${count.toLocaleString("fr-FR")} sûrs`;
}

/** Ce qu'annonce la confirmation de « Ranger les N sûrs ». */
export function tidyPlan(lot: ReturnType<typeof tidyLot>): string {
  const parts: string[] = [];
  if (lot.propositions.length)
    parts.push(`${counted(lot.propositions.length, "proposition sûre acceptée", "propositions sûres acceptées")}`);
  if (lot.renamed.length) parts.push(`${counted(lot.renamed.length, "fichier renommé", "fichiers renommés")}`);
  return `${parts.join(", ")}. Chaque geste se note au journal, et « Annuler » le défait.`;
}

/** « Artiste : les marees hautes → Les Marées Hautes ». */
export function propositionLine(proposition: Pick<FicheProposition, "field" | "before" | "value">): string {
  const label = FIELD_LABELS[proposition.field] ?? proposition.field;
  const before = proposition.before ? fieldValue(proposition.field, proposition.before) : "vide";
  return `${label} : ${before} → ${fieldValue(proposition.field, proposition.value)}`;
}

/** « 03_un.mp3 → Ada - Un.mp3 ». */
export function nameLine(title: Pick<Arrival, "path" | "to">): string {
  const name = title.path.split("/").pop() ?? title.path;
  return title.to ? `${name} → ${title.to}` : name;
}

/** Où est un titre de la banque : « Rotation » ou le dossier de sa collection. */
export function shelfOf(title: Pick<ArrivalTwin, "zone" | "collection">): string {
  return title.zone === "rotation" ? "Rotation" : title.collection || "Collections";
}

/** « Doublon possible : nuit · avant.mp3 ». */
export function duplicateLine(twins: ArrivalTwin[]): string {
  const places = twins.map((twin) => `${shelfOf(twin)} · ${twin.path.split("/").pop() ?? twin.path}`);
  return `${twins.length === 1 ? "Doublon possible" : "Doublons possibles"} : ${places.join(", ")}`;
}

/** Ce que « Ranger » a fait, pour le message en bas de l'écran. */
export function tidiedMessage(
  titles: number,
  decided: Pick<Decided, "written" | "waiting" | "failed" | "stale">,
  renamed: number,
  kept: number,
): { text: string; tone: "success" | "error" | "info" } {
  const parts = [`${counted(titles, "titre rangé", "titres rangés")} :`];
  const did: string[] = [];
  if (decided.written) did.push(counted(decided.written, "valeur écrite", "valeurs écrites"));
  if (renamed) did.push(counted(renamed, "fichier renommé", "fichiers renommés"));
  parts.push(did.length ? `${did.join(", ")}.` : "rien n'a changé.");
  const left: string[] = [];
  if (decided.waiting.length)
    left.push(
      `${counted(decided.waiting.length, "valeur s'écrira", "valeurs s'écriront")} après le passage à l'antenne`,
    );
  if (decided.failed.length || decided.stale)
    left.push(
      counted(decided.failed.length + decided.stale, "valeur ne s'est pas écrite", "valeurs ne se sont pas écrites"),
    );
  if (kept) left.push(counted(kept, "fichier garde son nom", "fichiers gardent leur nom"));
  if (left.length) parts.push(`${left.join(" ; ")}.`);
  const tone = decided.failed.length || decided.stale || kept ? "error" : did.length ? "success" : "info";
  return { text: parts.join(" "), tone };
}
