import type { BankTitle, FicheField } from "./bankTitles.ts";
import type { EditLot } from "./titleEdits.ts";

/**
 * La santé de la banque (FON-72) : ce qui cloche, compté et rangé par nature,
 * comme le moteur le rend (`GET /media/health.json`). Il compte à part : tant que
 * `computing` vaut vrai, la console redemande. La vue « À ranger » en fait des
 * tâches (`bankTasks.ts`, FON-92).
 */

/** Un titre que le moteur nomme, avec ce que sa correction lui ferait. */
export type HealthTitle = BankTitle & {
  /** Le nom que le modèle lui donne (fichiers mal nommés). */
  to?: string;
  /** Son genre, « Archive » retiré (FON-77). */
  genre_without?: string;
  /** L'artiste et le titre que donne le nom du fichier après son numéro de piste (FON-92). */
  guess?: { artist: string; title: string } | null;
};

export type SpellingGroup = {
  key: string;
  spellings: Array<{ value: string; count: number }>;
  suggested: string;
  count: number;
  titles: HealthTitle[];
};

export type DuplicateGroup = { label: string; titles: HealthTitle[] };

export type BankHealth = {
  model: string;
  figures: {
    titles: number;
    complete: number;
    families: Array<{ value: string; label: string; count: number }>;
    without_family: number;
    /** The known verdicts, only while the verdict is switched on (FON-80). */
    verdicts?: { oui: number; mixte: number; non: number };
  };
  spellings: { count: number; titles: number; groups: SpellingGroup[] };
  duplicates: { count: number; titles: number; groups: DuplicateGroup[] };
  misnamed: { count: number; titles: HealthTitle[] };
  /** Les titres dont l'artiste est un numéro de piste (FON-92). Absent d'un moteur plus ancien. */
  numbered?: { count: number; titles: HealthTitle[] };
  incomplete: { count: number; fields: Array<{ field: FicheField; count: number }> };
  archive: { count: number; titles: HealthTitle[] };
  unindexed: { count: number; paths: string[] };
};

export type HealthAnswer = {
  computing: boolean;
  /** À l'heure de Paris, ou null avant le premier compte. */
  computed_at: string | null;
  error: string | null;
  health: BankHealth | null;
};

/** Ce qu'un lot prend, comme le moteur : la fiche (FON-66) et le renommage (FON-68). */
export const MAX_LOT = 500;
/** Tant que le compte tourne, la console redemande à ce rythme. */
export const POLL_MS = 1500;

export function healthPath(model: string, refresh = false): string {
  const params = new URLSearchParams({ model });
  if (refresh) params.set("refresh", "1");
  return `/media/health.json?${params.toString()}`;
}

export function plural(count: number, one: string, many: string): string {
  return `${count.toLocaleString("fr-FR")} ${count === 1 ? one : many}`;
}

/**
 * « 140 « oui » sur 340 verdicts connus, 41 % » : la part des « oui » parmi les
 * verdicts connus, en titres (FON-80). null quand le verdict est éteint.
 */
export function verdictLine(figures: BankHealth["figures"]): string | null {
  if (!figures.verdicts) return null;
  const { oui, mixte, non } = figures.verdicts;
  const known = oui + mixte + non;
  if (!known) return "Aucun verdict connu pour l'instant.";
  const share = Math.round((oui / known) * 100);
  const rest = [mixte ? plural(mixte, "mixte", "mixtes") : "", non ? `${non.toLocaleString("fr-FR")} « non »` : ""]
    .filter(Boolean)
    .join(", ");
  return `${oui.toLocaleString("fr-FR")} « oui » sur ${plural(known, "verdict connu", "verdicts connus")}, ${share} %${rest ? ` (${rest})` : ""}`;
}

/** Le nombre de titres qu'un lot prend, et ce qu'il en laisse pour le suivant. */
export function lotOf<T>(titles: T[]): { taken: T[]; left: number } {
  return { taken: titles.slice(0, MAX_LOT), left: Math.max(0, titles.length - MAX_LOT) };
}

export function archiveAction(count: number): string {
  return `Retirer « Archive » de ${plural(Math.min(count, MAX_LOT), "fiche", "fiches")}`;
}

/**
 * Le lot qui retire « Archive » : chaque titre garde ses autres genres. Ce que la
 * console a montré part avec : un titre changé depuis refuse le lot (FON-66).
 */
export function archiveLot(titles: HealthTitle[]): EditLot {
  return {
    titles: lotOf(titles).taken.map((title) => ({
      id: title.id,
      values: { genre: title.genre_without ?? "" },
      expected: { genre: title.genre },
    })),
  };
}

/** « 4 fichiers de plus » sous une liste coupée. */
export function moreLine(count: number, shown: number, what: [string, string]): string {
  const more = count - shown;
  return more > 0 ? `et ${plural(more, ...what)} de plus` : "";
}
