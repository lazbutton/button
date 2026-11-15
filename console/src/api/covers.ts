/**
 * Les pochettes des fiches (FON-83) : la console ne les montre que par leur lien, quand la station les
 * montre, et seulement depuis un hôte d'images des sources. Pur : pas de React, testable en node.
 *
 * Le moteur ne rend déjà que ces hôtes-là (`COVER_DOMAINS`, `engine/radiotomate/fiches/covers.py`) ;
 * la console ne s'y fie pas, et la politique de contenu ne les admet pas d'autres
 * (`docker/security-headers.conf.template`).
 */

/** Deezer, Apple Music et Bandcamp : leurs images, chacun avec ses sous-domaines. */
export const COVER_DOMAINS = ["dzcdn.net", "mzstatic.com", "bcbits.com"] as const;

/** Le lien d'une pochette, s'il est sûr : en HTTPS, sur un hôte d'images des sources. Sinon null. */
export function coverUrl(value: unknown): string | null {
  const raw = typeof value === "string" ? value.trim() : "";
  if (!raw || raw.length > 500 || /\s/.test(raw)) return null;
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" || url.username || url.password || (url.port && url.port !== "443")) return null;
  const host = url.hostname.toLowerCase();
  return COVER_DOMAINS.some((domain) => host.endsWith(`.${domain}`)) ? url.href : null;
}
