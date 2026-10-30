/** Comment s'est terminée une connexion au flux du casque. */
export type StreamEnd = {
  /** Le serveur a fermé le flux. Sinon : une erreur, ou plus un octet depuis `stallMs`. */
  closed: boolean;
  /** La connexion a débité `steadyMs` au moins : le flux avait repris. */
  steady: boolean;
};

export type StreamWatch = {
  /** Sans un octet pendant ce temps, `stall` coupe la connexion. */
  stallMs: number;
  /** Une connexion qui débite depuis ce temps a repris. */
  steadyMs: number;
  /** Faux quand le casque n'attend plus rien de cette connexion. */
  alive: () => boolean;
  stall: () => void;
  onChunk: (chunk: Uint8Array) => void;
  /** Appelé une fois, quand la connexion a débité `steadyMs`. */
  onSteady: () => void;
};

/**
 * Lit une connexion au flux du casque, paquet par paquet, jusqu'à sa fin. Un
 * serveur peut accepter la connexion puis la fermer aussitôt, ou la garder
 * ouverte sans plus rien envoyer : `steady` dit le premier cas, `stall` coupe
 * le second.
 */
export async function readStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  watch: StreamWatch,
): Promise<StreamEnd> {
  const openedAt = Date.now();
  let steady = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const arm = () => {
    clearTimeout(timer);
    timer = setTimeout(watch.stall, watch.stallMs);
  };
  arm();
  try {
    while (watch.alive()) {
      const { done, value } = await reader.read();
      if (done) return { closed: true, steady };
      if (!value.byteLength) continue;
      arm();
      if (!steady && Date.now() - openedAt >= watch.steadyMs) {
        steady = true;
        watch.onSteady();
      }
      watch.onChunk(value);
    }
  } catch {
    /* coupée, ou muette depuis stallMs */
  } finally {
    clearTimeout(timer);
  }
  return { closed: false, steady };
}
