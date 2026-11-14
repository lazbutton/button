import type { BankFacet, BankTitle } from "./bankTitles.ts";
import type { EditOutcome, Tone } from "./titleEdits.ts";

/**
 * Les étiquettes de la station (FON-74) : poser et retirer une étiquette sur un
 * lot de titres, par `POST /media/titles/tags.json`. Une étiquette ne vit que
 * dans la bibliothèque, jamais dans le fichier. Les règles sont dans le moteur
 * (engine/radiotomate/services/station_tags.py) : la console les suit pour dire
 * tout de suite ce qui ne passera pas. Sans React.
 */

export const TAGS_JSON = "/media/titles/tags.json";
export const MAX_TAG = 40;
// Ni barre droite, le séparateur du champ, ni virgule, que Beets lit comme une
// fin de requête, ni guillemet, ni signe de contrôle.
const REFUSED = /[|,"\\\u0000-\u001f\u007f]/;

/** Une étiquette telle que le moteur l'écrit : en minuscules, ses espaces tassés. */
export function cleanTag(raw: string): string {
  return raw.normalize("NFC").split(/\s+/).filter(Boolean).join(" ").toLocaleLowerCase("fr");
}

/** Pourquoi le moteur refusera cette étiquette, ou rien. */
export function tagProblem(raw: string): string {
  const tag = cleanTag(raw);
  if (!tag) return "Une étiquette a au moins une lettre.";
  if (REFUSED.test(tag)) return "Une étiquette ne prend ni barre droite, ni virgule, ni guillemet : ils couperaient une sélection de titres.";
  if ([...tag].length > MAX_TAG) return `Une étiquette tient en ${MAX_TAG} signes.`;
  return "";
}

/** Les étiquettes d'un champ du journal, `|instrumental|nuit|`. */
export function parseTags(value: string): string[] {
  return value.split("|").filter((part) => part.trim());
}

function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLocaleLowerCase("fr");
}

/** Les étiquettes que portent ces titres, chacune avec son nombre de titres. */
export function tagsOnTitles(titles: Array<Pick<BankTitle, "etiquettes">>): BankFacet[] {
  const counts = new Map<string, number>();
  for (const title of titles) for (const tag of title.etiquettes ?? []) counts.set(tag, (counts.get(tag) ?? 0) + 1);
  return [...counts]
    .map(([value, count]) => ({ value, label: value, count }))
    .sort((a, b) => a.value.localeCompare(b.value, "fr"));
}

/**
 * Les étiquettes de la station à proposer : celles qui tiennent ce qui est tapé,
 * accents et casse oubliés, sans celles déjà choisies ; les plus portées d'abord.
 */
export function tagSuggestions(facets: BankFacet[], typed: string, chosen: string[], max = 12): BankFacet[] {
  const wanted = fold(cleanTag(typed));
  return facets
    .filter((facet) => facet.value && !chosen.includes(facet.value) && fold(facet.value).includes(wanted))
    .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value, "fr"))
    .slice(0, max);
}

/** La liste des étiquettes à poser, celle-ci ajoutée ; ou pourquoi elle ne l'est pas. */
export function withTag(chosen: string[], raw: string): { tags: string[]; problem: string } {
  const problem = tagProblem(raw);
  if (problem) return { tags: chosen, problem };
  const tag = cleanTag(raw);
  return { tags: chosen.includes(tag) ? chosen : [...chosen, tag], problem: "" };
}

function quoted(tags: string[]): string {
  const names = tags.map((tag) => `« ${tag} »`);
  return names.length > 1 ? `${names.slice(0, -1).join(", ")} et ${names[names.length - 1]}` : names[0];
}

function titles(count: number): string {
  return count === 1 ? "1 titre" : `${count} titres`;
}

/** Ce que dit la console une fois les étiquettes posées ou retirées. */
export function taggedMessage(outcome: EditOutcome, add: string[], remove: string[]): { text: string; tone: Tone } {
  if (!outcome.written) return { text: "Rien n'a changé : ces titres avaient déjà ces étiquettes.", tone: "info" };
  const on = titles(outcome.written);
  if (add.length + remove.length === 1) {
    const tag = quoted([...add, ...remove]);
    return { text: `Étiquette ${tag} ${add.length ? "posée sur" : "retirée de"} ${on}.`, tone: "success" };
  }
  const parts: string[] = [];
  if (add.length) parts.push(`${quoted(add)} ${add.length === 1 ? "posée" : "posées"}`);
  if (remove.length) parts.push(`${quoted(remove)} ${remove.length === 1 ? "retirée" : "retirées"}`);
  return { text: `Étiquettes changées sur ${on} : ${parts.join(", ")}.`, tone: "success" };
}
