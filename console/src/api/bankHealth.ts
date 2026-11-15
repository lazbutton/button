import type { BankTitle, FicheField, Ranking } from "./bankTitles.ts";
import { FIELD_LABELS } from "./bankTitles.ts";
import type { EditLot } from "./titleEdits.ts";

/**
 * La santé de la banque (FON-72) : ce qui cloche, compté et rangé par nature,
 * comme le moteur le rend (`GET /media/health.json`). Il compte à part : tant que
 * `computing` vaut vrai, la console redemande.
 */

/** Un titre que le moteur nomme, avec ce que sa correction lui ferait. */
export type HealthTitle = BankTitle & {
  /** Le nom que le modèle lui donne (fichiers mal nommés). */
  to?: string;
  /** Son genre, « Archive » retiré (FON-77). */
  genre_without?: string;
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
  };
  spellings: { count: number; titles: number; groups: SpellingGroup[] };
  duplicates: { count: number; titles: number; groups: DuplicateGroup[] };
  misnamed: { count: number; titles: HealthTitle[] };
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

/** « 7 sur 8 fiches complètes, 88 % ». */
export function completeLine(figures: BankHealth["figures"]): string {
  const { titles, complete } = figures;
  if (titles === 0) return "La banque est vide.";
  const share = Math.round((complete / titles) * 100);
  return `${complete.toLocaleString("fr-FR")} sur ${plural(titles, "fiche complète", "fiches complètes")}, ${share} %`;
}

/** « 3 familles », et les plus grandes, avec leur nombre de titres. */
export function familiesLine(figures: BankHealth["figures"], shown = 3): string {
  const { families } = figures;
  if (!families.length) return "Aucune famille encore.";
  const top = families
    .slice(0, shown)
    .map((family) => `${family.label} (${family.count.toLocaleString("fr-FR")})`)
    .join(", ");
  return `${plural(families.length, "famille", "familles")} : ${top}${families.length > shown ? "…" : ""}`;
}

/** Combien de choses clochent, tout compté : le titre de la vue. */
export function problemsCount(health: BankHealth): number {
  return (
    health.spellings.count +
    health.duplicates.count +
    health.misnamed.count +
    health.incomplete.count +
    health.archive.count +
    health.unindexed.count
  );
}

/** « « Les Marées Hautes » s'écrit de 3 façons, sur 5 titres ». */
export function spellingLine(group: SpellingGroup): string {
  return `« ${group.suggested} » s'écrit de ${group.spellings.length} façons, sur ${plural(group.count, "titre", "titres")}`;
}

export function spellingAction(group: SpellingGroup): string {
  return `Écrire partout « ${group.suggested} »`;
}

/** Le nombre de titres qu'un lot prend, et ce qu'il en laisse pour le suivant. */
export function lotOf<T>(titles: T[]): { taken: T[]; left: number } {
  return { taken: titles.slice(0, MAX_LOT), left: Math.max(0, titles.length - MAX_LOT) };
}

/** « Renommer 31 fichiers » ; au-delà d'un lot, les suivants après. */
export function renameAction(count: number): string {
  return `Renommer ${plural(Math.min(count, MAX_LOT), "fichier", "fichiers")}`;
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

/** Les champs vides qui ont un groupe dans le tableau, rangé sur ce champ. */
const RANKED_FIELDS: Partial<Record<FicheField, Ranking>> = { artist: "artist", album: "album", famille: "famille" };

/** Le tableau qui montre les titres sans ce champ, ou null quand il ne se range pas par lui. */
export function emptyFieldTable(field: FicheField): { ranger: Ranking; groupe: string } | null {
  const ranking = RANKED_FIELDS[field];
  return ranking ? { ranger: ranking, groupe: "" } : null;
}

/** « 12 sans album ». */
export function incompleteLine(field: FicheField, count: number): string {
  return `${plural(count, "fiche", "fiches")} sans ${FIELD_LABELS[field]}`;
}

/** « 03_un.mp3 → Ada - Un.mp3 ». */
export function renameLine(title: HealthTitle): string {
  const name = title.path.split("/").pop() ?? title.path;
  return title.to ? `${name} → ${title.to}` : name;
}

/** Où est un titre : « Rotation » ou le dossier de sa collection, et son nom. */
export function placeLine(title: Pick<HealthTitle, "path" | "collection" | "zone">): string {
  const name = title.path.split("/").pop() ?? title.path;
  const shelf = title.zone === "rotation" ? "Rotation" : title.collection || "Collections";
  return `${shelf} · ${name}`;
}

/** « 4 fichiers de plus » sous une liste coupée. */
export function moreLine(count: number, shown: number, what: [string, string]): string {
  const more = count - shown;
  return more > 0 ? `et ${plural(more, ...what)} de plus` : "";
}
