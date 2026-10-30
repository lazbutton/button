/**
 * Le pupitre (page Antenne) : raccourci Suivant, ancre à venir, alerte, temps.
 * Pur : pas de React, testable en node.
 */

/** Deux appuis sur Espace plus rapprochés que ça ne passent qu'un titre. */
export const SKIP_GUARD_MS = 1500;

/** Les éléments où Espace a déjà un sens : on ne le détourne pas. */
const OWN_SPACE_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT", "BUTTON", "A", "SUMMARY", "AUDIO", "VIDEO"]);
const OWN_SPACE_ROLES = new Set([
  "button",
  "checkbox",
  "link",
  "menuitem",
  "menuitemcheckbox",
  "menuitemradio",
  "option",
  "radio",
  "slider",
  "switch",
  "tab",
  "textbox",
]);

export type KeyTarget = { tag: string; role: string | null; editable: boolean } | null;

/** Un champ ou un contrôle : Espace y garde son sens (taper, cliquer, cocher). */
export function ownsSpace(target: KeyTarget): boolean {
  if (!target) return false;
  if (target.editable) return true;
  if (OWN_SPACE_TAGS.has(target.tag.toUpperCase())) return true;
  return Boolean(target.role && OWN_SPACE_ROLES.has(target.role));
}

/** Espace = Suivant, sauf sur un contrôle, à la répétition, ou trop tôt après un passage. */
export function spaceSkips(input: { target: KeyTarget; repeat: boolean; lastSkipAt: number; now: number }): boolean {
  if (input.repeat) return false;
  if (input.now - input.lastSkipAt < SKIP_GUARD_MS) return false;
  return !ownsSpace(input.target);
}

export function mmss(totalSec: number): string {
  const sec = Math.max(0, Math.round(totalSec));
  const hours = Math.floor(sec / 3600);
  const minutes = Math.floor((sec % 3600) / 60);
  const seconds = String(sec % 60).padStart(2, "0");
  return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${seconds}` : `${minutes}:${seconds}`;
}

/** « 1:07 / 3:47 » sous la barre d'avancée. */
export function progressLabel(elapsedSec: number, durationSec: number): string {
  return `${mmss(Math.min(elapsedSec, durationSec))} / ${mmss(durationSec)}`;
}

/** La prochaine ancre d'horloge : « Ancre :00 dans 7:20 ». Au-delà d'une heure, l'heure seule. */
export function anchorHint(item: { at: string; minute?: number } | null, now: Date): string | null {
  if (!item) return null;
  const start = Date.parse(item.at);
  if (!Number.isFinite(start)) return null;
  const name = item.minute != null ? `Ancre :${String(item.minute).padStart(2, "0")}` : "Ancre";
  const inSec = Math.max(0, Math.round((start - now.getTime()) / 1000));
  if (inSec >= 3600) return null;
  return inSec < 1 ? `${name} maintenant` : `${name} dans ${mmss(inSec)}`;
}

export type DeskAlert = {
  tone: "silence" | "problem";
  /** Stable, lu par les lecteurs d'écran. */
  title: string;
  /** Change avec le temps (secondes de silence) : pas annoncé. */
  live: string;
  help: string;
};

/**
 * Bandeau du pupitre : seulement quand quelque chose ne va pas. `lastAnswer`,
 * l'heure de la dernière réponse d'un moteur qui ne répond plus, passe avant le
 * reste : il date de ce moment-là.
 */
export function deskAlert(
  status: { tone: string; label: string; cause: string },
  lastAnswer: string | null = null,
): DeskAlert | null {
  if (lastAnswer != null) {
    // L'heure va dans l'aide, annoncée : elle ne change pas tant que dure la panne.
    return {
      tone: "problem",
      title: "Automate injoignable",
      live: "",
      help: `Le pupitre ne reçoit plus de nouvelles depuis ${lastAnswer} : le titre et la file affichés peuvent avoir changé.`,
    };
  }
  if (status.tone === "silence") {
    return {
      tone: "silence",
      title: "Silence à l’antenne",
      live: status.label.replace(/^Silence\s*/, ""),
      help: "Les auditeurs n’entendent plus de son utile. Passe au titre suivant ou lance un son.",
    };
  }
  if (status.tone !== "problem") return null;
  const cause = status.cause || "Problème";
  const help =
    cause === "Sortie Icecast coupée"
      ? "Le moteur tourne, mais le flux public ne part plus vers les auditeurs."
      : cause === "Battement perdu"
        ? "Le moteur ne reçoit plus de nouvelles du playout : l’antenne peut être figée."
        : "Le moteur ne joint plus le playout : l’antenne peut être coupée.";
  return { tone: "problem", title: cause, live: "", help };
}

/** Pré-écoute d'un résultat de bibliothèque, servi par le catalogue. */
export function previewUrl(id: string): string {
  return `/library/media/${encodeURIComponent(id)}`;
}

/**
 * Pourquoi une pré-écoute s'est arrêtée, d'après le statut que le catalogue
 * rend pour la même adresse (null : pas de réponse). L'élément audio ne le dit pas.
 */
export function previewFailure(status: number | null): string {
  if (status === 401) return "Session expirée : recharge la page et reconnecte-toi.";
  if (status === null || status >= 500) return "Pré-écoute impossible : le catalogue ne répond pas.";
  return "Pré-écoute impossible : le fichier ne répond pas.";
}
