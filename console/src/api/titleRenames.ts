/**
 * Renommer des fichiers d'après leur fiche (FON-68) : ce que la console envoie à
 * `POST /media/titles/rename.json`, et ce qu'elle dit de la réponse. Le nom se
 * forme dans le moteur (engine/radiotomate/services/bank_names.py), jamais ici :
 * l'aperçu le donne. Sans React.
 */

export type RenameModel = "artiste-titre" | "artiste-album-titre" | "titre";

export const RENAME_MODELS: Array<{ value: RenameModel; label: string }> = [
  { value: "artiste-titre", label: "Artiste - Titre" },
  { value: "artiste-album-titre", label: "Artiste - Album - Titre" },
  { value: "titre", label: "Titre" },
];

/** Un lot prend 500 titres au plus : le moteur refuse au-delà. */
export const MAX_RENAMES = 500;

export type RenameState =
  | "rename"
  | "same"
  | "taken"
  | "incomplete"
  | "busy"
  | "missing"
  | "renamed"
  | "failed"
  | "left";

export type RenameTitle = {
  id: number;
  label: string;
  /** Son chemin sous la banque. */
  path: string;
  /** Le chemin qu'il prendrait, ou `null`. */
  to: string | null;
  state: RenameState;
  reason: string;
};

export type RenameAnswer = { dry_run: boolean; titles: RenameTitle[]; entry: number | null; left: number[] };

export type RenameChoice = { model: RenameModel; byArtist: boolean };

export const DEFAULT_CHOICE: RenameChoice = { model: "artiste-titre", byArtist: false };

/** Le choix gardé par le navigateur, s'il se lit : sinon, celui par défaut. */
export function parseChoice(raw: string | null | undefined): RenameChoice {
  try {
    const value = JSON.parse(raw ?? "") as Partial<RenameChoice>;
    const model = RENAME_MODELS.find((item) => item.value === value.model)?.value;
    return { model: model ?? DEFAULT_CHOICE.model, byArtist: value.byArtist === true };
  } catch {
    return DEFAULT_CHOICE;
  }
}

/** Le dossier et le nom d'un chemin sous la banque. */
export function splitPath(path: string): { folder: string; name: string } {
  const cut = path.lastIndexOf("/");
  return cut < 0 ? { folder: "", name: path } : { folder: path.slice(0, cut), name: path.slice(cut + 1) };
}

/** Ce que l'aperçu compte : les fichiers qui prennent un nouveau nom, et les autres. */
export function renameCounts(titles: RenameTitle[]): { rename: number; same: number; kept: number } {
  const rename = titles.filter((title) => title.state === "rename").length;
  const same = titles.filter((title) => title.state === "same").length;
  return { rename, same, kept: titles.length - rename - same };
}

/** Une raison en phrase : le moteur en rend aussi de courtes, comme « déjà là ». */
export function sentence(reason: string): string {
  const text = reason.trim();
  if (!text) return "";
  return `${text[0].toUpperCase()}${text.slice(1)}${/[.!?]$/.test(text) ? "" : "."}`;
}

/** Pourquoi des titres gardent leur nom, chaque raison une fois, en phrases. */
export function keptReasons(titles: RenameTitle[], max = 3): string[] {
  const reasons = titles
    .filter((title) => !["rename", "renamed", "same"].includes(title.state))
    .map((title) => sentence(title.reason))
    .filter(Boolean);
  return [...new Set(reasons)].slice(0, max);
}

function files(count: number): string {
  return count === 1 ? "1 fichier" : `${count} fichiers`;
}

export function renameLabel(count: number): string {
  return `Renommer ${files(count)}`;
}

/** Ce que dit l'aperçu, en une phrase : combien changent de nom, combien gardent le leur. */
export function previewSummary(titles: RenameTitle[]): string {
  const { rename, same, kept } = renameCounts(titles);
  const parts: string[] = [];
  parts.push(
    rename
      ? `${files(rename)} ${rename === 1 ? "prendra le nom de sa fiche" : "prendront le nom de leur fiche"}.`
      : "Aucun fichier ne change de nom.",
  );
  if (same) parts.push(`${files(same)} ${same === 1 ? "le porte" : "le portent"} déjà.`);
  if (kept) parts.push(`${files(kept)} ${kept === 1 ? "garde son" : "gardent leur"} nom, comme dit ci-dessous.`);
  return parts.join(" ");
}

/** Plusieurs réponses, quand le moteur a renvoyé une partie du lot faute de temps. */
export function mergeAnswers(answers: RenameAnswer[]): { titles: RenameTitle[]; entries: number[] } {
  const byId = new Map<number, RenameTitle>();
  for (const answer of answers) for (const title of answer.titles) byId.set(title.id, title);
  return {
    titles: [...byId.values()],
    entries: answers.map((answer) => answer.entry).filter((entry): entry is number => entry != null),
  };
}

export type Tone = "success" | "error" | "info";

/** Ce que dit la console après le renommage. */
export function renamedMessage(titles: RenameTitle[]): { text: string; tone: Tone } {
  const done = titles.filter((title) => title.state === "renamed").length;
  const missed = titles.filter((title) => ["failed", "left", "taken", "busy", "missing", "incomplete"].includes(title.state));
  const reasons = keptReasons(missed);
  if (!done && !missed.length) return { text: "Rien n'a changé : les fichiers portaient déjà ces noms.", tone: "info" };
  const head = done ? `${files(done)} ${done === 1 ? "renommé" : "renommés"}.` : "Aucun fichier renommé.";
  if (!missed.length) return { text: head, tone: "success" };
  const left = `${files(missed.length)} ${missed.length === 1 ? "garde son" : "gardent leur"} nom.`;
  return { text: [head, left, ...reasons].join(" "), tone: "error" };
}

/** Ce que dit la console après « Annuler » un renommage. */
export function unrenamedMessage(outcome: { written: number; kept: unknown[] }): { text: string; tone: Tone } {
  const back = outcome.written;
  const kept = outcome.kept.length;
  const head = back
    ? `${files(back)} ${back === 1 ? "a repris son" : "ont repris leur"} nom d'avant.`
    : "Aucun fichier n'a repris son nom d'avant.";
  if (!kept) return { text: head, tone: back ? "success" : "info" };
  return {
    text: `${head} ${kept === 1 ? "Un fichier garde le sien : il a changé de place depuis, ou il passe à l'antenne." : `${kept} fichiers gardent le leur : ils ont changé de place depuis, ou ils passent à l'antenne.`}`,
    tone: "info",
  };
}
