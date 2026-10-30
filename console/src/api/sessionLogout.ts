import { isUnreachableStatus } from "./engineUnreachable.ts";
import { READ_DEADLINE_MS, withDeadline } from "./readDeadline.ts";

/**
 * La déconnexion ferme la session sur le moteur, puis la console oublie la
 * sienne, quoi qu'il réponde (`apiLogout`, dans `client.ts`). Pur : pas de
 * React, testable en node.
 */

/**
 * Le cookie de session reste valable tant que le moteur n'a pas fermé la
 * session : automate revenu, un rechargement de la page la rouvre.
 */
export const LOGOUT_UNREACHED_MESSAGE =
  "La déconnexion n’a pas atteint l’automate : ta session est peut-être encore ouverte. Reconnecte-toi puis déconnecte-toi quand il répond.";

/**
 * Demande la fermeture de la session, avec le délai des lectures : un moteur
 * muet ne retient pas la déconnexion. Rend false si la demande n'a pas atteint
 * le moteur : sans réponse, ou une réponse du relais qui dit le moteur
 * injoignable. Toute autre réponse vient du moteur, même une erreur.
 */
export async function closeSession(
  request: (signal: AbortSignal) => Promise<Pick<Response, "status">>,
): Promise<boolean> {
  try {
    const response = await withDeadline(READ_DEADLINE_MS, request, () => new Error("late"));
    return !isUnreachableStatus(response.status);
  } catch {
    return false;
  }
}
