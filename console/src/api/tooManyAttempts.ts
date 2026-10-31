/**
 * Trop d'essais de connexion depuis cette adresse : le moteur, ou nginx avant
 * lui, répond 429 `{error: "too_many_attempts", retry_in}`, le délai en
 * secondes. L'adresse est bloquée, jamais le compte.
 */
export function isTooManyAttempts(status: number, detail: string | undefined): boolean {
  return status === 429 && detail === "too_many_attempts";
}

/** Ce que dit le formulaire de connexion. `retryIn` : le délai en secondes, s'il est connu. */
export function tooManyAttemptsMessage(retryIn: unknown): string {
  const seconds = Number(retryIn);
  if (!Number.isFinite(seconds) || seconds <= 0) return "Trop d’essais. Réessaie plus tard.";
  const minutes = Math.ceil(seconds / 60);
  return `Trop d’essais. Réessaie dans ${minutes} ${minutes > 1 ? "minutes" : "minute"}.`;
}
