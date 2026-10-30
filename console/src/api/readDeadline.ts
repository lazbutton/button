import { withIdleDeadline } from "./sendDeadline.ts";

/**
 * Le temps qu'a une lecture du moteur, corps compris. Un moteur qui accepte la
 * connexion sans répondre, boucle Quart bloquée ou réseau qui perd les
 * paquets, ne fait jamais échouer la lecture de lui-même : nginx l'attend une
 * heure. Le moteur attend lui-même le scheduler jusqu'à 8 s
 * (/antenne/state.json) : ce délai le laisse répondre. Les sondages qui
 * attendaient la même lecture échouent avec elle : un moteur muet se dit
 * injoignable au bout de ce délai.
 */
export const READ_DEADLINE_MS = 10_000;

/**
 * Lance `read` avec un signal qui l'abandonne au bout de `ms`. Passé ce délai,
 * la lecture rejette avec `late()`, même si `read` ne regarde pas le signal.
 * Une réponse ou une erreur arrivée avant garde la sienne.
 */
export function withDeadline<T>(ms: number, read: (signal: AbortSignal) => Promise<T>, late: () => Error): Promise<T> {
  const controller = new AbortController();
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(late());
      controller.abort();
    }, ms);
    read(controller.signal).then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error: unknown) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

/**
 * Comme withDeadline, pour une lecture dont le corps peut être long à venir,
 * comme un son lu en entier avant d'être joué. Le délai vaut pour la réponse,
 * puis repart à chaque morceau du corps (withIdleDeadline, `sendDeadline.ts`) :
 * un son lent qui avance n'est jamais coupé. Un corps qui n'avance plus, ou
 * qui se coupe en route, rejette avec `late()`. Une erreur de `answer`, comme
 * celle d'un statut, garde la sienne.
 */
export function withBodyDeadline(
  ms: number,
  answer: (signal: AbortSignal) => Promise<Response>,
  late: () => Error,
): Promise<Blob> {
  return withIdleDeadline(
    ms,
    async (signal, alive) => {
      const response = await answer(signal);
      alive();
      const parts: Uint8Array<ArrayBuffer>[] = [];
      if (response.body) {
        const reader = response.body.getReader();
        try {
          for (let chunk = await reader.read(); !chunk.done; chunk = await reader.read()) {
            parts.push(chunk.value);
            alive();
          }
        } catch {
          throw late();
        }
      }
      return new Blob(parts, { type: response.headers.get("Content-Type") ?? "" });
    },
    late,
  );
}
