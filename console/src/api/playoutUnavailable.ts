/**
 * Le moteur répond, mais son playout, Liquidsoap, ne répond pas : un geste
 * d'antenne reçoit 502 `playout_unavailable`. L'ordre a pu passer si
 * Liquidsoap était seulement lent : on vérifie l'antenne avant de recommencer.
 * Sans ce code, un 502 veut dire que l'automate ne répond pas.
 */
export const PLAYOUT_UNAVAILABLE_MESSAGE = "Le playout ne répond pas. Vérifie l’antenne avant de recommencer.";

export function isPlayoutUnavailable(status: number, detail: string | undefined): boolean {
  return status === 502 && detail === "playout_unavailable";
}
