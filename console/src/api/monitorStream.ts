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

/**
 * Attend la réponse du serveur du flux, `ms` au plus. Un serveur peut accepter
 * la connexion sans jamais répondre : une machine injoignable à mi-chemin, un
 * proxy qui attend son amont. Passé ce délai, `giveUp` abandonne la demande,
 * et l'attente échoue. `readStream` prend le relais une fois la réponse là.
 */
export function answerWithin<T>(pending: Promise<T>, ms: number, giveUp?: () => void): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => {
      giveUp?.();
      reject(new Error("timeout"));
    }, ms);
    pending.finally(() => clearTimeout(timer)).then(resolve, reject);
  });
}

/** Ce que l'élément audio a joué depuis son chargement, en secondes : la somme de `audio.played`. */
export function playedSeconds(played: Pick<TimeRanges, "length" | "start" | "end">): number {
  let seconds = 0;
  for (let i = 0; i < played.length; i++) seconds += played.end(i) - played.start(i);
  return seconds;
}

/** Une adresse IPv4 écrite en quatre nombres, sinon null. */
function ipv4(host: string): number[] | null {
  const parts = host.split(".");
  if (parts.length !== 4 || !parts.every((part) => /^\d{1,3}$/.test(part))) return null;
  const octets = parts.map(Number);
  return octets.every((octet) => octet <= 255) ? octets : null;
}

/**
 * Un flux sur la machine ou le réseau local, que le casque lit avec un tampon court :
 * localhost, une adresse IPv4 privée (RFC 1918) ou de lien local, la boucle ou le lien
 * local en IPv6, un nom sans point, ou en `.local`, `.lan`, `.home.arpa` ou `.internal`.
 * Le reste est loin, et garde le tampon large : un VPN comme Tailscale, dans la plage
 * 100.64.0.0/10 ou en IPv6 unique locale (fc00::/7), compris.
 */
export function isNearHost(hostname: string): boolean {
  const host = hostname
    .trim()
    .toLowerCase()
    .replace(/^\[(.*)\]$/, "$1")
    .replace(/\.$/, "");
  if (!host) return false;
  if (host === "localhost" || host.endsWith(".localhost")) return true;
  const v4 = ipv4(host);
  if (v4) {
    const [a, b] = v4;
    return (
      a === 127 || a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 169 && b === 254)
    );
  }
  // IPv6 : la boucle, et le lien local, fe80::/10.
  if (host.includes(":")) return host === "::1" || /^fe[89ab][0-9a-f]:/.test(host);
  return !host.includes(".") || /\.(local|lan|home\.arpa|internal)$/.test(host);
}
