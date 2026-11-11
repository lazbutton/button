import type { Cart, SkippedFile } from "./types";

/** Le chemin que le moteur donne au dossier entier : au-delà de 2000 sons, le bac n'en prend plus rien. */
export const WHOLE_FOLDER = ".";

/** Les premiers fichiers refusés se lisent d'emblée, les suivants sur demande. */
export const SKIPPED_SHOWN = 3;

/**
 * Les fichiers du dossier d'un bac que le moteur n'a pas pris, avec leur raison.
 * Un moteur plus ancien ne les donne pas, et un relais ne suit pas de dossier :
 * rien à montrer.
 */
export function skippedFiles(cart: Pick<Cart, "mode" | "skipped_files">): SkippedFile[] {
  if (cart.mode === "relay" || !Array.isArray(cart.skipped_files)) return [];
  return cart.skipped_files.filter((file) => typeof file?.path === "string" && typeof file.reason === "string");
}

/**
 * Ce que dit l'encart des fichiers refusés. `folder` : le dossier du bac, vu du
 * dossier de la station. C'est là qu'un fichier se remplace ou se retire : le
 * retirer de Dropbox ne le retire pas de la station.
 */
export function skippedNotice(files: SkippedFile[], folder: string): { title: string; help: string } | null {
  if (!files.length) return null;
  if (files.some((file) => file.path === WHOLE_FOLDER)) {
    return {
      title: "Le dossier du bac a trop de fichiers",
      help: `Dans le dossier de la station, déplace une partie des fichiers de ${folder} ailleurs : sous 2000, le bac reprend ceux qui y arrivent.`,
    };
  }
  if (files.length === 1) {
    return {
      title: "1 fichier n'est pas entré dans le bac",
      help: `Dans le dossier de la station, sous ${folder}, remplace-le par un son que l'automate lit, ou retire-le.`,
    };
  }
  return {
    title: `${files.length} fichiers ne sont pas entrés dans le bac`,
    help: `Dans le dossier de la station, sous ${folder}, remplace-les par des sons que l'automate lit, ou retire-les.`,
  };
}

/** Le nom d'un fichier refusé : son chemin dans le dossier du bac, ou le dossier lui-même. */
export function skippedName(file: SkippedFile, folder: string): string {
  return file.path === WHOLE_FOLDER ? folder : file.path;
}

/** Les fichiers montrés d'emblée, et ceux qui attendent qu'on les demande : jamais un seul. */
export function skippedSplit(files: SkippedFile[]): { shown: SkippedFile[]; more: SkippedFile[] } {
  if (files.length <= SKIPPED_SHOWN + 1) return { shown: files, more: [] };
  return { shown: files.slice(0, SKIPPED_SHOWN), more: files.slice(SKIPPED_SHOWN) };
}
