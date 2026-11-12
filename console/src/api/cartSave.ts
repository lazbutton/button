import type { Cart } from "./types";
import { UNKNOWN_ROUTE_MESSAGE } from "./unknownRoute.ts";

/**
 * Les réglages qu'enregistre un bac, sous leur nom dans le moteur, et ce qu'en
 * dit le message. `PUT /carts/{id}.json` n'écrit que ceux qu'il reçoit.
 */
const SETTINGS = {
  title: "le nom",
  notes: "les notes",
  mode: "la lecture",
  bank_folder: "le dossier de la banque",
  ident_pads: "les pads d'idents",
  url: "l'adresse du flux",
  max_duration: "la durée maximale",
} as const;

export type CartSetting = keyof typeof SETTINGS;

/** Une valeur sous une seule forme : le moteur rend `null` ce que la console envoie vide. */
function plain(setting: CartSetting, value: unknown): string | number | boolean | null {
  if (setting === "ident_pads") return Boolean(value);
  if (setting === "max_duration") {
    const seconds = Number(value);
    return Number.isFinite(seconds) && seconds !== 0 ? seconds : null;
  }
  return value == null ? "" : String(value);
}

/**
 * Les réglages envoyés que le moteur a changés depuis que la page a lu le bac,
 * et pas pour la valeur envoyée. Sans eux, renvoyer l'enregistrement n'écrase
 * rien : le bac a changé ailleurs, mais pas là, comme quand un son y entre.
 */
export function changedElsewhere(read: Cart, fresh: Cart, sent: Record<string, unknown>): CartSetting[] {
  return (Object.keys(SETTINGS) as CartSetting[]).filter((setting) => {
    if (!(setting in sent)) return false;
    const now = plain(setting, fresh[setting]);
    return now !== plain(setting, read[setting]) && now !== plain(setting, sent[setting]);
  });
}

/** « le nom », « le nom et les notes », « le nom, les notes et la lecture ». */
function listed(items: string[]): string {
  if (items.length < 2) return items.join("");
  return `${items.slice(0, -1).join(", ")} et ${items[items.length - 1]}`;
}

function what(settings: CartSetting[]): string {
  return settings.length ? ` : ${listed(settings.map((setting) => SETTINGS[setting]))}` : "";
}

/** Ce que dit le formulaire quand le moteur refuse un bac changé ailleurs : la page l'a relu, la saisie reste. */
export function changedText(settings: CartSetting[]): string {
  return `Ce bac vient d'être modifié ailleurs${what(settings)}. La page s'est mise à jour, et tes changements restent à l'écran : vérifie-les, puis enregistre.`;
}

/** Le même refus, quand son formulaire n'est plus à l'écran : la saisie est partie avec lui. */
export function lostText(title: string, settings: CartSetting[]): string {
  return `« ${title} » vient d'être modifié ailleurs${what(settings)}. Tes changements n'y ont pas été enregistrés.`;
}

/**
 * Le bac a été supprimé ailleurs. `title` : son nom, quand la page montre déjà
 * un autre bac ; sinon, c'est celui qu'elle quitte.
 */
export function goneText(title: string | null): string {
  if (title == null) return "Ce bac n'existe plus : il a peut-être été supprimé.";
  return `« ${title} » n'existe plus : il a peut-être été supprimé. Tes changements n'y ont pas été enregistrés.`;
}

/** Le refus du moteur pour une version dépassée : un 409, sur le champ `version`. */
export function isVersionRefusal(status: number, field: string | undefined, message: string): boolean {
  return status === 409 && (field === "version" || /changed since version/i.test(message));
}

/**
 * Le bac n'existe plus : 404 sur sa route. Un moteur trop ancien pour la route
 * répond aussi 404, mais `client.ts` lui donne un autre message.
 */
export function isGoneRefusal(status: number, message: string): boolean {
  return status === 404 && message !== UNKNOWN_ROUTE_MESSAGE;
}

/** Ce que la page envoie : les réglages, avec la version du bac sur lequel la saisie a commencé. */
export function withVersion(payload: Record<string, unknown>, cart: Pick<Cart, "version">): Record<string, unknown> {
  return cart.version == null ? payload : { ...payload, version: cart.version };
}

/**
 * Le brouillon d'un formulaire quand le bac est relu : ce que la personne a
 * changé reste, le reste suit le moteur. `before` : le bac tel que le
 * formulaire l'avait lu.
 */
export function keepEdits<T extends Record<string, unknown>>(current: T, before: T, fresh: T): T {
  const next = { ...fresh };
  for (const key of Object.keys(fresh) as (keyof T)[]) {
    if (current[key] !== before[key]) next[key] = current[key];
  }
  return next;
}

/**
 * Une saisie reste à enregistrer une fois le bac relu. Tant que c'est le cas, le
 * formulaire garde la version du bac où elle a commencé : un changement fait
 * ailleurs entre-temps fait refuser l'enregistrement, au lieu d'être écrasé.
 */
export function unsavedEdits<T extends Record<string, unknown>>(current: T, before: T, fresh: T): boolean {
  const next = keepEdits(current, before, fresh);
  return Object.keys(fresh).some((key) => next[key] !== fresh[key]);
}

export type CartSaveIo = {
  /** `PUT /carts/{id}.json` : le bac tel que le moteur l'a écrit. */
  put: (body: Record<string, unknown>) => Promise<Cart>;
  /** Le bac relu dans le moteur, et montré par la page ; `null` s'il n'existe plus. */
  read: () => Promise<Cart | null>;
  /** Le moteur a refusé la version envoyée. */
  refused: (caught: unknown) => boolean;
  /** Le moteur ne connaît plus le bac. */
  gone: (caught: unknown) => boolean;
};

export type CartSaveResult =
  | { status: "saved"; cart: Cart }
  /** `cart` : le bac relu, que la page montre maintenant. */
  | { status: "changed"; settings: CartSetting[]; cart: Cart }
  | { status: "gone" };

/** Ce que la page rend au formulaire qui a enregistré : le bac écrit, ou le refus à montrer avec le bac relu. */
export type CartAnswer = { status: "saved"; cart: Cart } | { status: "changed"; cart: Cart; text: string };

/** Les deux formulaires d'un bac : ses réglages, et l'éditeur d'un relais. */
export type CartForm = "settings" | "relay";

/**
 * Le formulaire qui a enregistré est encore à l'écran, sur le même bac : il montre
 * le refus lui-même. Sinon la page le dit : la personne a changé de bac, fermé
 * les réglages, ou le relais est devenu ailleurs un bac de sons. La page le juge
 * d'après le bac relu ; le formulaire, lui, sait s'il est encore celui qui a
 * enregistré (`stillHere`), même rouvert ou revenu sur le même bac entre-temps.
 */
export function formStillShown(
  form: CartForm,
  savedId: number,
  fresh: Pick<Cart, "mode">,
  shown: { id: number | null; settings: boolean },
): boolean {
  if (shown.id !== savedId) return false;
  return form === "settings" ? shown.settings : fresh.mode === "relay";
}

/**
 * Enregistre les réglages d'un bac avec sa version. `read` est le bac sur lequel
 * la saisie a commencé. Si le moteur refuse sa version, la page relit le bac.
 * Quand rien de ce qu'elle envoie n'a changé ailleurs, elle renvoie une fois,
 * avec la nouvelle version : un son ajouté, ou un moteur plus ancien dont chaque
 * tirage montait la version, ne fait pas refuser l'enregistrement. Sinon, elle
 * dit ce qui a changé.
 */
export async function saveCartSettings(
  read: Cart,
  payload: Record<string, unknown>,
  io: CartSaveIo,
): Promise<CartSaveResult> {
  let base = read;
  for (let attempt = 1; ; attempt += 1) {
    try {
      return { status: "saved", cart: await io.put(withVersion(payload, base)) };
    } catch (caught) {
      if (io.gone(caught)) return { status: "gone" };
      if (!io.refused(caught)) throw caught;
    }
    const fresh = await io.read();
    if (!fresh) return { status: "gone" };
    const settings = changedElsewhere(read, fresh, payload);
    if (settings.length || attempt >= 2) return { status: "changed", settings, cart: fresh };
    base = fresh;
  }
}
