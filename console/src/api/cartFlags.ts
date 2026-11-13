import { LEGACY_HABILLAGE_FOLDERS, legacyIsHabillageFolder } from "./legacyLayout.ts";
import type { BankResponse, Cart } from "./types";

/** The folders of habillage a bac may follow, as /media/bank.json says them; an older engine does not. */
export function habillageFoldersOf(payload: Pick<BankResponse, "habillage"> | null | undefined): string[] {
  const said = payload?.habillage;
  return Array.isArray(said) && said.length ? said : LEGACY_HABILLAGE_FOLDERS;
}

/** The engine says where a bac's folder is; an older engine leaves its path to read. */
export function isHabillageCart(cart: Pick<Cart, "bank_folder" | "bank_zone">): boolean {
  if (cart.bank_zone !== undefined) return cart.bank_zone === "habillage";
  return legacyIsHabillageFolder(cart.bank_folder);
}

export type BacFilter = "tous" | "fichiers" | "habillage" | "relais";

export function cartMatchesBacFilter(cart: Cart, filter: BacFilter): boolean {
  if (filter === "tous") return true;
  if (filter === "relais") return cart.mode === "relay";
  if (filter === "habillage") return isHabillageCart(cart) && cart.mode !== "relay";
  return cart.mode !== "relay";
}

export function bacFilterFor(cart: Cart): Exclude<BacFilter, "tous"> {
  if (cart.mode === "relay") return "relais";
  if (isHabillageCart(cart)) return "habillage";
  return "fichiers";
}

/** Pads d’idents : le drapeau, sinon le cart encore nommé Jingles. */
export function identCart(carts: Cart[]): Cart | undefined {
  return carts.find((cart) => cart.ident_pads) ?? carts.find((cart) => cart.title === "Jingles");
}

/** URL de relais : schéma, hôte, et un chemin (le moteur refuse une URL sans chemin). */
export function relayUrlOk(value: string): boolean {
  const text = value.trim();
  try {
    const url = new URL(text);
    if (url.protocol !== "http:" && url.protocol !== "https:") return false;
    if (!url.hostname) return false;
    return text.replace(/^[a-z][a-z0-9+.-]*:\/\/[^/]+/i, "").startsWith("/");
  } catch {
    return false;
  }
}
