/**
 * The order of a cart's view, and its sounds sent to another cart (FON-70). A
 * view sorts without touching the order the cart plays in, until someone applies
 * it. Pure logic, tested alongside.
 */

/** What a view of a cart sorts by: the cart's own order, or a column. */
export type ViewSort = "rank" | "title" | "artist" | "duration" | "last_played";

export const VIEW_SORTS: Array<{ id: ViewSort; label: string }> = [
  { id: "rank", label: "Ordre du bac" },
  { id: "title", label: "Titre" },
  { id: "artist", label: "Artiste" },
  { id: "duration", label: "Durée" },
  { id: "last_played", label: "Dernier passage" },
];

export type SortableSound = { id: number; rank: number; title: string; duration: number; last_played: string | null };
type Split = (raw: string) => { artist: string; title: string };

function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLocaleLowerCase("fr");
}

/**
 * The sounds in the view's order. Title and artist come from the sound's name, «
 * Artiste - Titre », by `split`; a sound without an artist goes last. By last
 * play, the one heard longest ago first, and one never heard before all.
 */
export function sortSounds<T extends SortableSound>(sounds: T[], sort: ViewSort, split: Split): T[] {
  const byRank = [...sounds].sort((a, b) => a.rank - b.rank);
  if (sort === "rank") return byRank;
  const text = (sound: T) => {
    const parts = split(sound.title);
    return sort === "artist" ? parts.artist : parts.title;
  };
  return byRank.sort((a, b) => {
    if (sort === "duration") return a.duration - b.duration;
    if (sort === "last_played") {
      if (a.last_played === b.last_played) return 0;
      if (!a.last_played) return -1;
      if (!b.last_played) return 1;
      return a.last_played < b.last_played ? -1 : 1;
    }
    const left = fold(text(a));
    const right = fold(text(b));
    if (!left !== !right) return left ? -1 : 1;
    return left.localeCompare(right, "fr");
  });
}

/** Whether the view already shows the cart's order: nothing to apply. */
export function sameOrder(sorted: SortableSound[], sounds: SortableSound[]): boolean {
  const byRank = [...sounds].sort((a, b) => a.rank - b.rank);
  return sorted.length === byRank.length && sorted.every((sound, index) => sound.id === byRank[index].id);
}

/** The band above a sorted view: what it shows, and that the cart plays as before. */
export function orderBanner(sort: ViewSort, mode: string): string {
  const label = VIEW_SORTS.find((item) => item.id === sort)?.label.toLowerCase() ?? sort;
  if (mode === "random") {
    return `Vue triée par ${label}. En Aléatoire, le bac n'a pas d'ordre : ce tri ne sert qu'à la vue.`;
  }
  return `Vue triée par ${label} : le bac passe toujours dans son ordre, tant qu'on n'applique pas celui-ci.`;
}

/** What a move or a copy to another cart did, said in a toast. */
export function transferSummary(
  copy: boolean,
  done: number,
  skipped: Array<{ title: string; reason: string }>,
  target: string,
): { text: string; tone: "success" | "error" | "info" } {
  const verb = copy ? (done === 1 ? "copié" : "copiés") : done === 1 ? "déplacé" : "déplacés";
  const head = done ? `${done === 1 ? "1 son" : `${done} sons`} ${verb} ${copy ? "dans" : "vers"} « ${target} ».` : "";
  if (!skipped.length) return { text: head || `Rien n'a changé dans « ${target} ».`, tone: done ? "success" : "info" };
  const reasons = [...new Set(skipped.map((item) => item.reason))].join(", ");
  const rest = `${skipped.length === 1 ? "1 son est resté" : `${skipped.length} sons sont restés`} : ${reasons}.`;
  return { text: head ? `${head} ${rest}` : rest, tone: done ? "info" : "error" };
}
