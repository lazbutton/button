/**
 * Le temps qu'a un geste (POST, PUT, PATCH ou DELETE), réponse comprise. Un
 * moteur qui accepte la connexion sans répondre, boucle Quart bloquée ou réseau
 * qui perd les paquets, ne fait jamais échouer le geste de lui-même : nginx
 * l'attend une heure. Pour un geste, le moteur attend lui-même le scheduler
 * 5 s au plus : ce délai le laisse répondre.
 */
export const SEND_DEADLINE_MS = 10_000;

/** Lier un dossier de la banque à un bac : le moteur lit jusqu'à 2000 fichiers avant de répondre. */
export const BANK_SEND_DEADLINE_MS = 60_000;

/**
 * Un dépôt de sons dure le temps de les envoyer, plusieurs minutes sur un
 * réseau lent. Il n'est abandonné que s'il n'avance plus : aucun octet parti
 * pendant ce temps, ou pas de réponse ce temps après le dernier
 * (`withUploadDeadline`).
 */
export const UPLOAD_IDLE_MS = 30_000;

/** Un geste resté sans réponse : le moteur l'a peut-être fait, et le refaire peut le doubler. */
export const NO_ANSWER_MESSAGE = "L’automate ne répond pas. Le geste a peut-être été fait : vérifie avant de réessayer.";

/**
 * Comme withDeadline (`readDeadline.ts`), mais le délai repart à chaque appel
 * de `alive` : un envoi lent qui avance n'est jamais coupé. Passé `ms` sans
 * signe de vie, l'envoi rejette avec `late()` et son signal l'abandonne. Une
 * réponse ou une erreur arrivée avant garde la sienne.
 */
export function withIdleDeadline<T>(
  ms: number,
  send: (signal: AbortSignal, alive: () => void) => Promise<T>,
  late: () => Error,
): Promise<T> {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  return new Promise<T>((resolve, reject) => {
    const wait = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        reject(late());
        controller.abort();
      }, ms);
    };
    // Un signe de vie arrivé après l'abandon ne relance rien.
    const alive = () => {
      if (!controller.signal.aborted) wait();
    };
    wait();
    send(controller.signal, alive).then(
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
 * Le délai d'un dépôt, en deux temps. Tant que le corps part, un dépôt qui
 * n'avance plus est coupé, et rejette avec `unsent()` : nginx garde le corps
 * entier avant de le relayer, le moteur n'a rien reçu. Après le dernier octet
 * (`sent`), la réponse a tout le délai. Passé ce délai, le dépôt rejette avec
 * `unanswered()`, sans être coupé : le moteur écrit peut-être encore les
 * fichiers sous leur nom, et un dépôt coupé laisserait un son tronqué dans le
 * dossier du bac, que le scheduler y rattacherait.
 */
export function withUploadDeadline<T>(
  ms: number,
  send: (signal: AbortSignal, alive: () => void, sent: () => void) => Promise<T>,
  unsent: () => Error,
  unanswered: () => Error,
): Promise<T> {
  let allSent = false;
  const cut = new AbortController();
  return withIdleDeadline(
    ms,
    (signal, alive) => {
      signal.addEventListener("abort", () => {
        if (!allSent) cut.abort();
      });
      return send(cut.signal, alive, () => {
        allSent = true;
        alive();
      });
    },
    () => (allSent ? unanswered() : unsent()),
  );
}
