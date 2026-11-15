import type { BankHealth, DuplicateGroup, HealthTitle, SpellingGroup } from "./bankHealth.ts";
import { lotOf, plural } from "./bankHealth.ts";
import { FICHES_JSON } from "./fiches.ts";
import type { EditLot } from "./titleEdits.ts";
import { RENAME_MODELS, type RenameModel } from "./titleRenames.ts";

/**
 * La vue « À ranger » de Sons → Banque (FON-92) : ce qui attend une personne
 * dans la banque, en tâches, d'après le compte de sa santé (`GET
 * /media/health.json`, FON-72) et les fiches que la recherche en ligne propose
 * (`GET /fiches.json`, FON-26). Elle remplace les vues Arrivées et Santé, et
 * ouvre la relecture. Ce qui va bien ne s'y montre pas ; le nom des fichiers,
 * qui ne change rien à l'antenne, est facultatif. Sans React.
 */

export type TaskKey =
  | "unindexed"
  | "numbered"
  | "artist"
  | "title"
  | "review"
  | "spellings"
  | "duplicates"
  | "archive"
  | "names";

export type Task = {
  key: TaskKey;
  /** Ce qui cloche, compté : le titre de la tâche. */
  title: string;
  /** Ce que ça change, et comment faire. */
  why: string;
  /** Le nom des fichiers : rien ne change à l'antenne. */
  optional: boolean;
};

/** Le nombre de titres que la recherche en ligne propose de corriger, sans les lire. */
export const REVIEW_COUNT_PATH = `${FICHES_JSON}?limit=1`;

/** Ce qu'une tâche montre avant « et N de plus ». */
export const SHOWN = 5;

/** Un nombre comme la console l'écrit : « 7 123 ». */
function number(count: number): string {
  return count.toLocaleString("fr-FR");
}

function incomplete(health: BankHealth, field: "artist" | "title"): number {
  return health.incomplete.fields.find((row) => row.field === field)?.count ?? 0;
}

function numberedTitles(health: BankHealth): HealthTitle[] {
  return health.numbered?.titles ?? [];
}

/** « « 01 », « 02 »… » : les numéros pris pour artiste, deux au plus. */
export function numbersLine(titles: Pick<HealthTitle, "artist">[]): string {
  const numbers = [...new Set(titles.map((title) => title.artist))];
  const shown = numbers.slice(0, 2).map((number) => `« ${number} »`);
  return `${shown.join(", ")}${numbers.length > 2 ? "…" : ""}`;
}

/** Le libellé d'un modèle de nom : « Artiste - Titre ». */
export function modelLabel(model: RenameModel): string {
  return RENAME_MODELS.find((item) => item.value === model)?.label ?? model;
}

/**
 * Les tâches, dans l'ordre : ce que l'antenne montre ou ne joue pas d'abord,
 * puis le reste de la fiche, et le nom des fichiers à la fin, facultatif.
 * `review` : les titres que la recherche en ligne propose de corriger, ou null.
 */
export function tasksOf(health: BankHealth | null, review: number | null, model: RenameModel): Task[] {
  const tasks: Task[] = [];
  const one = (count: number, single: string, many: string) => (count === 1 ? single : many);
  if (health?.unindexed.count) {
    const count = health.unindexed.count;
    tasks.push({
      key: "unindexed",
      title: one(count, "1 fichier n'est pas dans la bibliothèque", `${number(count)} fichiers ne sont pas dans la bibliothèque`),
      why: `${one(count, "Il ne passe", "Ils ne passent")} pas à l'antenne. Un fichier déposé y entre en une minute : s'il reste ici, la boucle d'import ne sait pas le lire.`,
      optional: false,
    });
  }
  const numbered = health ? (health.numbered?.count ?? 0) : 0;
  if (health && numbered) {
    tasks.push({
      key: "numbered",
      title: one(numbered, "1 titre a un numéro pour artiste", `${number(numbered)} titres ont un numéro pour artiste`),
      why: `L'antenne affiche ${numbersLine(numberedTitles(health))} à la place de l'artiste.`,
      optional: false,
    });
  }
  const artist = health ? incomplete(health, "artist") : 0;
  if (artist) {
    tasks.push({
      key: "artist",
      title: plural(artist, "titre sans artiste", "titres sans artiste"),
      why: `${one(artist, "Il passe", "Ils passent")} à l'antenne sans nom d'artiste.`,
      optional: false,
    });
  }
  const title = health ? incomplete(health, "title") : 0;
  if (title) {
    tasks.push({
      key: "title",
      title: plural(title, "fiche sans titre", "fiches sans titre"),
      why: `${one(title, "Elle passe", "Elles passent")} à l'antenne sans titre. Le tableau, trié par titre, les montre en tête.`,
      optional: false,
    });
  }
  if (review) {
    tasks.push({
      key: "review",
      title: one(review, "1 titre a des corrections trouvées en ligne", `${number(review)} titres ont des corrections trouvées en ligne`),
      why: "La recherche des fiches les propose : rien ne s'écrit sans ton accord.",
      optional: false,
    });
  }
  if (health?.spellings.count) {
    const count = health.spellings.count;
    tasks.push({
      key: "spellings",
      title: one(count, "1 artiste s'écrit de plusieurs façons", `${number(count)} artistes s'écrivent de plusieurs façons`),
      why: `Le tableau et les sélections de titres ${one(count, "le comptent", "les comptent")} comme plusieurs artistes. Choisis la bonne graphie : elle s'écrit sur chaque titre.`,
      optional: false,
    });
  }
  if (health?.duplicates.count) {
    const count = health.duplicates.count;
    tasks.push({
      key: "duplicates",
      title: one(count, "1 titre est en double", `${number(count)} titres sont en double`),
      why: "Même artiste, même titre, même durée à 2 secondes près : il passe plus souvent qu'un autre. Écoute les copies dans le tableau, puis retire celle de trop.",
      optional: false,
    });
  }
  if (health?.archive.count) {
    const count = health.archive.count;
    tasks.push({
      key: "archive",
      title: one(count, "1 fiche porte le genre « Archive »", `${number(count)} fiches portent le genre « Archive »`),
      why: "L'ancienne boucle d'import l'écrivait dans chaque titre d'une collection. Le retirer garde les autres genres.",
      optional: false,
    });
  }
  if (health?.misnamed.count) {
    const count = health.misnamed.count;
    const label = modelLabel(model);
    tasks.push({
      key: "names",
      title: one(count, `1 fichier ne s'appelle pas « ${label} »`, `${number(count)} fichiers ne s'appellent pas « ${label} »`),
      why: `${one(count, "Son nom ne change", "Leur nom ne change")} rien à l'antenne. Le renommer d'après la fiche range le dossier de la station.`,
      optional: true,
    });
  }
  return tasks;
}

/** Ce que compte l'onglet « À ranger » : les tâches, sans le facultatif. */
export function tasksCount(tasks: Task[]): number {
  return tasks.filter((task) => !task.optional).length;
}

/** « Rien à signaler : doublons, … », ce que le compte a vérifié sans rien trouver. */
export function clearLine(health: BankHealth): string | null {
  const checks: Array<[boolean, string]> = [
    [health.duplicates.count === 0, "doublons"],
    [health.spellings.count === 0, "orthographe des artistes"],
    [incomplete(health, "artist") === 0 && incomplete(health, "title") === 0, "artistes et titres manquants"],
    [(health.numbered?.count ?? 0) === 0, "numéros pris pour artiste"],
    [health.unindexed.count === 0, "fichiers hors de la bibliothèque"],
  ];
  const clear = checks.filter(([ok]) => ok).map(([, label]) => label);
  return clear.length ? `Rien à signaler : ${clear.join(", ")}.` : null;
}

/** « 03_un.mp3 → Ada - Un.mp3 » : le nom d'un fichier, et celui que lui donne sa fiche. */
export function renameLine(title: Pick<HealthTitle, "path" | "to">): string {
  const name = title.path.split("/").pop() ?? title.path;
  return title.to ? `${name} → ${title.to}` : name;
}

/** « 01 - Ana - Fado.mp3 → Ana – Fado » : le nom du fichier, et la fiche qu'il donne. */
export function guessLine(title: Pick<HealthTitle, "path" | "guess">): string {
  const name = title.path.split("/").pop() ?? title.path;
  return title.guess ? `${name} → ${title.guess.artist} – ${title.guess.title}` : name;
}

/** Les titres dont le nom donne l'artiste et le titre, et les autres. */
export function numberedSplit(titles: HealthTitle[]): { guessed: HealthTitle[]; bare: HealthTitle[] } {
  return { guessed: titles.filter((title) => title.guess), bare: titles.filter((title) => !title.guess) };
}

/**
 * Le lot qui donne à ces titres l'artiste et le titre de leur nom de fichier.
 * Ce que la console a montré part avec : un titre changé depuis refuse le lot.
 */
export function numberedLot(titles: HealthTitle[]): EditLot {
  return {
    titles: lotOf(numberedSplit(titles).guessed).taken.map((title) => ({
      id: title.id,
      values: { artist: title.guess?.artist ?? "", title: title.guess?.title ?? "" },
      expected: { artist: title.artist, title: title.title },
    })),
  };
}

export function numberedAction(count: number): string {
  return count === 1 ? "Corriger d'après son nom" : `Corriger les ${count.toLocaleString("fr-FR")} d'après leur nom`;
}

/** « Les Marées Hautes (4) · les marees hautes (2) ». */
export function spellingsLine(group: SpellingGroup): string {
  return group.spellings.map((spelling) => `${spelling.value} (${spelling.count})`).join(" · ");
}

/** Le lot qui écrit une graphie sur chaque titre du groupe qui ne l'a pas. */
export function spellingLot(group: SpellingGroup, chosen: string): EditLot {
  return {
    titles: lotOf(group.titles.filter((title) => title.artist !== chosen)).taken.map((title) => ({
      id: title.id,
      values: { artist: chosen },
      expected: { artist: title.artist },
    })),
  };
}

export function spellingAction(chosen: string, count: number): string {
  return `Écrire « ${chosen} » sur ${plural(count, "titre", "titres")}`;
}

/** « avant.mp3 (Rotation), avant-bis.flac (nuit) » : chaque copie, et où elle est. */
export function copiesLine(group: DuplicateGroup): string {
  return group.titles
    .map((title) => {
      const name = title.path.split("/").pop() ?? title.path;
      const shelf = title.zone === "rotation" ? "Rotation" : title.collection || "Collections";
      return `${name} (${shelf})`;
    })
    .join(", ");
}

/** « Orage – Avant ». */
export function duplicateLabel(group: DuplicateGroup): string {
  const first = group.titles[0];
  return first ? `${first.artist} – ${first.title}` : group.label;
}

/** Les adresses du tableau qu'une tâche ouvre, comme `BankTable` les lit. */
export const TABLE_WITHOUT_ARTIST = { ranger: "artist", groupe: "" };
export const TABLE_BY_TITLE = { tri: "title" };
export const TABLE_BY_ARTIST = { ranger: "artist" };

export function tableOfDuplicate(group: DuplicateGroup): Record<string, string> {
  return { q: group.titles[0]?.title ?? "" };
}
