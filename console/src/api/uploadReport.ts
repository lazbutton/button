/**
 * Reconnaître un fichier dès l'envoi (FON-82) : ce que la banque sait d'un fichier que la vue Ajouter
 * vient d'envoyer. Pur : pas de React, testable en node.
 *
 * Un doublon se range comme les autres fichiers, et se signale ici, comme dans « À ranger » (FON-92) :
 * la console ne retire ni ne refuse rien. Le doublon est celui que la santé de la banque compte (FON-72).
 */

export const UPLOADS_JSON = "/fiches/envois.json";
/** Ce que la console suit à la fois, comme le moteur l'accepte. */
export const UPLOADS_MAX = 100;
/** Au-delà, un fichier qui n'est toujours pas dans la banque ne se redemande plus. */
export const UPLOADS_FOLLOW_MS = 30 * 60 * 1000;

export type UploadTitle = {
  id: number;
  artist: string;
  title: string;
  path: string;
  zone: string;
  collection: string;
};

export type UploadFileReport = {
  dest: string;
  name: string;
  in_bank: boolean;
  id: number | null;
  path: string | null;
  artist?: string;
  title?: string;
  duplicates: UploadTitle[];
  recognized: { artist: string; title: string; level: string; source: string } | null;
  searched: boolean;
};

export type UploadReport = { fiches: boolean; files: UploadFileReport[] };

export type UploadNote = { tone: "wait" | "warn" | "found" | "plain"; text: string };

export const uploadKey = (dest: string, name: string) => `${dest}\u0000${name}`;

/** Plus rien à attendre : le fichier est dans la banque, et la recherche l'a cherché, ou elle est éteinte. */
export function settled(file: UploadFileReport, fichesOn: boolean): boolean {
  return file.in_bank && (!fichesOn || file.searched);
}

function titleName(one: { artist: string; title: string }): string {
  return one.artist ? `${one.artist} - ${one.title}` : one.title;
}

/**
 * Ce que la file dit d'un fichier envoyé, dans l'ordre : le doublon d'abord, puis ce qu'il est.
 * `labelOf` nomme une collection comme la vue Ajouter la nomme.
 */
export function uploadNotes(
  file: UploadFileReport,
  fichesOn: boolean,
  labelOf: (collection: string) => string,
): UploadNote[] {
  if (!file.in_bank) return [{ tone: "wait", text: "En route vers la banque" }];
  const notes: UploadNote[] = [];
  const [first, ...more] = file.duplicates;
  if (first) {
    const where = first.collection ? ` (${labelOf(first.collection)})` : "";
    const others = more.length ? ` et ${more.length} autre${more.length === 1 ? "" : "s"}` : "";
    notes.push({ tone: "warn", text: `Doublon de ${titleName(first)}${where}${others}` });
  }
  if (file.recognized) {
    const { artist, title } = file.recognized;
    notes.push({ tone: "found", text: `Reconnu : ${artist ? `${artist}, ` : ""}${title}` });
  } else if (fichesOn && !file.searched) {
    notes.push({ tone: "wait", text: "Dans la banque, recherche en cours" });
  } else if (fichesOn) {
    notes.push({ tone: "plain", text: "Dans la banque, pas reconnu en ligne" });
  } else if (!first) {
    notes.push({ tone: "plain", text: "Dans la banque" });
  }
  return notes;
}

/** Le corps de la demande : chaque fichier par sa destination et son nom, sans doublon. */
export function uploadsBody(files: Array<{ dest: string; name: string }>): { files: Array<{ dest: string; name: string }> } {
  const seen = new Set<string>();
  const out: Array<{ dest: string; name: string }> = [];
  for (const file of files) {
    const key = uploadKey(file.dest, file.name);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ dest: file.dest, name: file.name });
    if (out.length === UPLOADS_MAX) break;
  }
  return { files: out };
}
