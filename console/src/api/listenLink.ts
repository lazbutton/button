/**
 * « Retrouver ce titre » (FON-84) : le réglage de la station, et le lien du titre en cours.
 * Pur : pas de React, testable en node.
 */
import type { LiveSnapshot, ListenLinkSettings } from "./types.ts";

/** Le formulaire : la clé partenaire s'écrit, elle ne se relit jamais (`key_set` dit seulement qu'elle existe). */
export type ListenLinkForm = {
  enabled: boolean;
  url: string;
  /** Vide : on garde la clé posée. */
  key: string;
  /** Efface la clé posée. */
  clearKey: boolean;
};

export function listenLinkForm(settings: ListenLinkSettings): ListenLinkForm {
  return { enabled: settings.enabled, url: settings.url ?? "", key: "", clearKey: false };
}

export function listenLinkChanged(form: ListenLinkForm, settings: ListenLinkSettings): boolean {
  return (
    form.enabled !== settings.enabled ||
    form.url.trim() !== (settings.url ?? "") ||
    form.key.trim() !== "" ||
    form.clearKey
  );
}

/** Le corps du PUT : la clé n'y est que saisie ou effacée, jamais renvoyée telle qu'elle est gardée. */
export function listenLinkBody(form: ListenLinkForm): Record<string, unknown> {
  const body: Record<string, unknown> = { enabled: form.enabled, url: form.url.trim() };
  if (form.clearKey) body.key = "";
  else if (form.key.trim()) body.key = form.key.trim();
  return body;
}

/**
 * Le lien du titre en cours, s'il y en a un sûr. Jamais pour un relevé périmé, ni pour
 * autre chose qu'une adresse web : le moteur la garde déjà ainsi, la console ne s'y fie pas.
 */
export function listenLink(live: LiveSnapshot | null, stale: boolean): string | null {
  if (!live || stale || live.status === "offline") return null;
  const raw = typeof live.listen_url === "string" ? live.listen_url.trim() : "";
  if (!raw || /\s/.test(raw)) return null;
  try {
    const url = new URL(raw);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}
