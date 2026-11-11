/**
 * Le code source de la version en service, que l'AGPL doit à chaque personne qui se sert
 * de la console. La station le sert elle-même : l'image de la console porte l'archive du
 * code de son commit, que nginx donne à tout compte connecté, sous `/code-source/`
 * ([ADR 0018](../../../docs/decisions/0018-la-station-sert-son-code-source.md)). Pur : pas de
 * React, testable en node.
 */

/** Le dépôt de BUTTON : le lien quand la station ne sert pas d'archive, en dev par exemple. */
export const DEFAULT_SOURCE_URL = "https://github.com/lazbutton/button";

/** Où nginx sert le code de la version, à une session (`docker/nginx.conf.template`). */
export const SOURCE_PATH = "/code-source/";

/** `source.json`, que `scripts/version.py source` écrit à côté de l'archive : il la nomme. */
export const SOURCE_DESCRIPTOR = `${SOURCE_PATH}source.json`;

/** La console n'attend `source.json` que 5 s : passé ce délai, le lien mène au dépôt. */
export const SOURCE_DEADLINE_MS = 5_000;

export type SourceArchive = { file: string };

// Un nom de fichier seul, jamais un chemin : il se met au bout de SOURCE_PATH.
const FILE = /^[A-Za-z0-9][A-Za-z0-9._-]*\.tar\.gz$/;

/** L'archive que nomme `source.json`, ou null si la réponse ne la nomme pas comme il faut. */
export function sourceArchive(payload: unknown): SourceArchive | null {
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) return null;
  const file = (payload as { file?: unknown }).file;
  return typeof file === "string" && FILE.test(file) ? { file } : null;
}

/**
 * `GET /code-source/source.json`, avec la session. `retry` : pas de réponse sûre pour
 * l'instant, comme une session échue, un moteur qui ne répond pas à nginx, ou pas de
 * réponse dans le délai ; la console relira. Un 404, une image construite sans archive,
 * ou une page HTML à la place, comme en dev, sont une réponse : pas d'archive.
 */
export type SourceRead = { archive: SourceArchive | null; retry: boolean };

export async function readSourceArchive(
  fetcher: typeof fetch = fetch,
  deadlineMs = SOURCE_DEADLINE_MS,
): Promise<SourceRead> {
  try {
    const response = await fetcher(SOURCE_DESCRIPTOR, {
      cache: "no-store",
      credentials: "same-origin",
      signal: AbortSignal.timeout(deadlineMs),
    });
    if (response.status === 404) return { archive: null, retry: false };
    if (!response.ok) return { archive: null, retry: true };
    if (!/json/i.test(response.headers.get("content-type") ?? "")) return { archive: null, retry: false };
    return { archive: sourceArchive(await response.json()), retry: false };
  } catch (caught) {
    // Un JSON illisible ne le sera pas plus en relisant.
    return { archive: null, retry: !(caught instanceof SyntaxError) };
  }
}

/** Le lien « Code source » : son adresse, et le nom du fichier quand il le télécharge. */
export type SourceLink = { href: string; download?: string };

/**
 * D'abord le lien que règle la station pour une version modifiée : `source_url`, posé
 * sur brand.json (`withStation`, api/station.ts). Puis l'archive de la version en
 * service, que sert la station. Puis le dépôt de BUTTON.
 */
export function sourceLink(sourceUrl: string | undefined, archive: SourceArchive | null): SourceLink {
  const own = sourceUrl?.trim();
  if (own) return { href: own };
  if (archive) return { href: `${SOURCE_PATH}${archive.file}`, download: archive.file };
  return { href: DEFAULT_SOURCE_URL };
}
