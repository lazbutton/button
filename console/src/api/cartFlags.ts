import type { Cart } from "./types";

export function isHabillageCart(cart: Cart): boolean {
  return (cart.bank_folder || "").startsWith("30-habillage");
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
