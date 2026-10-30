/**
 * Le moteur accepte le mot de passe et pose le cookie de session, mais le
 * navigateur peut le refuser. La sonde qui suit répond alors 401, comme pour une
 * session expirée : seul le moment les distingue (`StudioLogin`, dans
 * `SessionGate.tsx`). Pur : pas de React, testable en node.
 */

/**
 * Sonde la session juste après un mot de passe accepté. Seul un défaut de session
 * veut dire que le cookie n'a pas tenu : une autre erreur suit le chemin habituel.
 */
export async function cookieRefused(
  probe: () => Promise<unknown>,
  unauthenticated: (caught: unknown) => boolean,
): Promise<boolean> {
  try {
    await probe();
    return false;
  } catch (caught) {
    return unauthenticated(caught);
  }
}

/** Ce que dit le formulaire de connexion quand la session manque juste après. */
export function cookieRefusedMessage(protocol: string, cookieEnabled: boolean): string {
  const refused = "Mot de passe accepté, mais le navigateur a refusé le cookie de session";
  // Un navigateur qui bloque les cookies les refuse tous, en http:// comme en
  // https://. En https://, l'attribut Secure n'y est pour rien.
  if (!cookieEnabled || protocol === "https:") return `${refused}. Autorise les cookies pour ce site, puis réessaie.`;
  return `${refused} : il ne passe qu’en HTTPS. Ouvre la console avec son adresse en https://.`;
}
