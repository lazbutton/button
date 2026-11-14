/**
 * Titles of the bank in a cart, without a copy (FON-69). The sound plays the
 * title where it is, in the rotation or a collection; the cart only keeps its
 * path. Pure logic, tested alongside.
 */

/** A cart that plays a title of the bank, as `/media/titles.json` names it. */
export type TitleCart = { id: number; title: string };

/** What the console reads of a cart to offer it: its id, its name, its mode. */
export type CartChoice = { id: number; title: string; mode: string };

/** The carts that take a title: every one but a relay, which plays a stream. */
export function cartsThatTake<T extends CartChoice>(carts: T[]): T[] {
  return carts.filter((cart) => cart.mode !== "relay").sort((a, b) => a.title.localeCompare(b.title, "fr"));
}

function quoted(names: string[]): string {
  const said = names.map((name) => `« ${name} »`);
  return said.length > 1 ? `${said.slice(0, -1).join(", ")} et ${said[said.length - 1]}` : said[0];
}

/**
 * Before titles leave the bank: which carts play them, and what becomes of their
 * sound. Empty when no cart plays any of them.
 */
export function cartsBeforeRemoval(titles: Array<{ title: string; path: string; carts?: TitleCart[] }>): string {
  const played = titles.filter((title) => title.carts?.length);
  if (!played.length) return "";
  const names = [...new Set(played.flatMap((title) => (title.carts ?? []).map((cart) => cart.title)))];
  const bacs = `${names.length === 1 ? "le bac" : "les bacs"} ${quoted(names)}`;
  if (played.length === 1 && titles.length === 1) {
    const name = played[0].title || played[0].path.split("/").pop() || "Ce titre";
    return `« ${name} » est joué par ${bacs} : son son y restera, « Indisponible », jusqu'à ce qu'on le retire du bac.`;
  }
  const count = played.length === 1 ? "Un de ces titres est joué" : `${played.length} de ces titres sont joués`;
  return `${count} par ${bacs} : leurs sons y resteront, « Indisponible », jusqu'à ce qu'on les retire des bacs.`;
}

/** What adding titles to a cart did, said in a toast. */
export function addedToCart(added: number, asked: number, cart: string): { text: string; tone: "success" | "info" } {
  if (added === 0) return { text: `Ces titres sont déjà dans le bac « ${cart} ».`, tone: "info" };
  const what = added === 1 ? "1 titre de la banque ajouté" : `${added} titres de la banque ajoutés`;
  const already = asked - added;
  const rest = already > 0 ? ` ${already === 1 ? "Un autre y était déjà." : `${already} autres y étaient déjà.`}` : "";
  return { text: `${what} au bac « ${cart} », sans copie.${rest}`, tone: "success" };
}

/** Why a cart opened in Dropbox does not show these sounds: it only sees its own folder. */
export const DROPBOX_NOTE =
  "Ces titres restent dans la banque, sans copie : un bac ouvert dans Dropbox ne les voit pas, il ne voit que les fichiers de son dossier.";
