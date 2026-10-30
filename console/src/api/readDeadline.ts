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
