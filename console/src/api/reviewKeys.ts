import { count, decidedMessage, type Decided, type FicheProposition, type FicheTitle } from "./fiches.ts";

/**
 * Relire au clavier (FON-78) : un titre à la fois, A accepte, R refuse, les
 * flèches passent au suivant ou reviennent, Z défait le dernier geste
 * (`POST /fiches/decisions/annuler.json`), Échap quitte. Pur : pas de React.
 */

export const REOPEN_JSON = "/fiches/decisions/annuler.json";

export type ReviewKey = "accept" | "refuse" | "next" | "previous" | "undo";

/** Ce qui reçoit la touche : un champ de saisie la garde. */
export type KeyTarget = { tagName?: string; isContentEditable?: boolean } | null | undefined;

const TYPING = new Set(["INPUT", "TEXTAREA", "SELECT"]);

/**
 * Le geste d'une touche, ou null. Une touche avec Ctrl, ⌘ ou Alt reste au
 * navigateur, comme une touche frappée dans un champ de saisie. A, R et Z
 * tenus enfoncés ne se répètent pas : un geste, une touche. Échap, Radix le
 * prend : il ferme la fenêtre.
 */
export function reviewKey(
  event: { key: string; ctrlKey?: boolean; metaKey?: boolean; altKey?: boolean; repeat?: boolean },
  target?: KeyTarget,
): ReviewKey | null {
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  if (target && (target.isContentEditable || TYPING.has((target.tagName ?? "").toUpperCase()))) return null;
  switch (event.key) {
    case "ArrowRight":
    case "ArrowDown":
      return "next";
    case "ArrowLeft":
    case "ArrowUp":
      return "previous";
  }
  if (event.repeat) return null;
  switch (event.key.toLowerCase()) {
    case "a":
      return "accept";
    case "r":
      return "refuse";
    case "z":
      return "undo";
    default:
      return null;
  }
}

/** Les propositions d'un titre qui attendent d'être relues. */
export function waitingIds(propositions: Array<Pick<FicheProposition, "id" | "state">>): number[] {
  return propositions.filter((one) => one.state === "proposée").map((one) => one.id);
}

/** Les titres à relire d'une page, sans ceux déjà dans la file. */
export function queueOf(titles: FicheTitle[], already: FicheTitle[] = []): FicheTitle[] {
  const seen = new Set(already.map((title) => title.id));
  return titles.filter((title) => !seen.has(title.id) && waitingIds(title.propositions).length > 0);
}

/** « 12 sur 87 » : le rang du titre montré, compté à partir de 1. */
export function progressText(index: number, total: number): string {
  return `${count(Math.min(index + 1, total))} sur ${count(total)}`;
}

export function titleName(title: Pick<FicheTitle, "title" | "path">): string {
  return title.title || title.path.split("/").pop() || title.path;
}

/** Ce qu'entend un lecteur d'écran en arrivant sur un titre. */
export function positionLine(index: number, total: number, name: string): string {
  return `${progressText(index, total)} : « ${name} ».`;
}

export type Gesture = { kind: "accept" | "refuse"; beetsId: number; ids: number[]; name: string };

/** Ce que dit un geste fait, avant le titre suivant. */
export function gestureLine(gesture: Pick<Gesture, "kind" | "name">, decided: Decided): string {
  if (gesture.kind === "refuse") return `« ${gesture.name} » refusé.`;
  const told = decidedMessage(decided);
  return `« ${gesture.name} » accepté. ${told.text}`;
}

/** Ce que dit Z une fois le geste défait. */
export function undoneLine(gesture: Pick<Gesture, "kind" | "name">, decided: Decided): string {
  const what = gesture.kind === "accept" ? "Acceptation défaite" : "Refus défait";
  const waiting = decided.waiting.length
    ? " Il passe à l'antenne : sa valeur d'avant reviendra après son passage."
    : " Il est de nouveau à relire.";
  return `${what} : « ${gesture.name} ».${waiting}`;
}

/** La fin de la file : ce qui a été décidé pendant la relecture. */
export function endLine(accepted: number, refused: number): string {
  if (!accepted && !refused) return "Tout est passé, sans geste.";
  const parts: string[] = [];
  if (accepted) parts.push(`${count(accepted)} titre${accepted === 1 ? "" : "s"} accepté${accepted === 1 ? "" : "s"}`);
  if (refused) parts.push(`${count(refused)} refusé${refused === 1 ? "" : "s"}`);
  return `Tout est relu : ${parts.join(", ")}.`;
}
