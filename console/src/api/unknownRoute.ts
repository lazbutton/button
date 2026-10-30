/**
 * Un moteur plus ancien que la console ne connaît pas la route : Quart répond
 * 404 avec la description par défaut de werkzeug, en anglais. Une ressource
 * introuvable, elle, garde son message.
 */
const WERKZEUG_NOT_FOUND = "The requested URL was not found on the server.";

export const UNKNOWN_ROUTE_MESSAGE = "Cette action demande un moteur plus récent. Mets à jour le moteur.";

export function isUnknownRoute(status: number, detail: string | undefined): boolean {
  return status === 404 && Boolean(detail?.startsWith(WERKZEUG_NOT_FOUND));
}
