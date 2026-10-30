/**
 * En prod, nginx relaie l'API du moteur. Moteur arrêté, nginx répond lui-même
 * 502, ou 504 si le moteur tarde, avec sa page HTML. Le moteur répond aussi
 * 502 ou 503 quand son scheduler ou son disque ne répond pas. Dans tous ces
 * cas, l'automate ne répond pas.
 */
const UNREACHABLE_STATUSES = [502, 503, 504];

/**
 * Le statut seul. Il suffit sur /login, où le moteur répond lui-même en HTML,
 * même pour refuser un mot de passe.
 */
export function isUnreachableStatus(status: number): boolean {
  return UNREACHABLE_STATUSES.includes(status);
}

/**
 * Les routes .json du moteur répondent en JSON : une erreur en HTML y vient
 * d'un relais. Hors de ces routes, comme pour un son, la console ne montre pas
 * davantage ce HTML. `detail` : le message de l'erreur, ou le début du corps
 * s'il n'est pas du JSON.
 */
export function isEngineUnreachable(status: number, detail: string | undefined): boolean {
  return isUnreachableStatus(status) || Boolean(detail?.startsWith("<"));
}
