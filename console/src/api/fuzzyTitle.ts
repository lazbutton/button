/** Accents, casse et ponctuation ignorés pour la recherche de titres. */
export function foldTitle(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function typoBudget(len: number): number {
  return Math.max(1, Math.floor(len / 4));
}

/** Distance de Damerau–Levenshtein (insert, delete, substitute, transposition). */
function damerau(a: string, b: string): number {
  if (a === b) return 0;
  const al = a.length;
  const bl = b.length;
  if (!al) return bl;
  if (!bl) return al;
  const d: number[][] = Array.from({ length: al + 1 }, (_, i) => {
    const row = new Array<number>(bl + 1);
    row[0] = i;
    return row;
  });
  for (let j = 0; j <= bl; j++) d[0][j] = j;
  for (let i = 1; i <= al; i++) {
    for (let j = 1; j <= bl; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
        d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
      }
    }
  }
  return d[al][bl];
}

function wordHits(hayWord: string, queryWord: string): boolean {
  if (hayWord.includes(queryWord)) return true;
  if (queryWord.length >= 4 && hayWord.length >= 4 && queryWord.includes(hayWord)) return true;
  if (Math.abs(hayWord.length - queryWord.length) > typoBudget(queryWord.length) + 1) return false;
  return damerau(hayWord, queryWord) <= typoBudget(queryWord.length);
}

export function fuzzyTitleMatch(haystack: string, needle: string): boolean {
  const query = foldTitle(needle);
  if (!query) return true;
  const hay = foldTitle(haystack);
  if (!hay) return false;
  if (hay.includes(query)) return true;
  const queryWords = query.split(" ").filter(Boolean);
  const hayWords = hay.split(" ").filter(Boolean);
  if (queryWords.length && queryWords.every((qw) => hayWords.some((hw) => wordHits(hw, qw)))) {
    return true;
  }
  return query.length <= 24 && damerau(hay, query) <= typoBudget(query.length);
}
