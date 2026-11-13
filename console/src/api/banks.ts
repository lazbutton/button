import { LEGACY_COLLECTIONS_FOLDER } from "./legacyLayout.ts";
import type { BankDestination } from "./soundsView";

/** Creates a collection, through the catalogue. */
export async function createBank(label: string, folder: string): Promise<BankDestination> {
  let response: Response;
  try {
    response = await fetch("/library/banks.json", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label, folder }),
    });
  } catch {
    throw new Error("Le catalogue ne répond pas. Réessaie dans un instant.");
  }
  const payload = (await response.json().catch(() => ({}))) as { destination?: BankDestination; error?: string };
  if (response.status === 401) throw new Error("Session expirée : recharge la page et reconnecte-toi.");
  if (!response.ok || !payload.destination) {
    throw new Error(payload.error?.trim() || "Création impossible. Réessaie.");
  }
  return payload.destination;
}

/** What inbox.json says of the collections. Missing from an older catalogue. */
export type CollectionsInfo = { folder: string };

/** The folder a collection is born in, from inbox.json, or the one an older catalogue has. */
export function collectionsFolderOf(payload: unknown): string {
  const collections = (payload as { collections?: Partial<CollectionsInfo> } | null)?.collections;
  const folder = typeof collections?.folder === "string" ? collections.folder.trim() : "";
  return folder || LEGACY_COLLECTIONS_FOLDER;
}

let knownFolder: string | null = null;

/** The folder of the collections, once read: it does not change while the page is open. */
export function knownCollectionsFolder(): string {
  return knownFolder ?? LEGACY_COLLECTIONS_FOLDER;
}

/** Asks the catalogue where a collection is born. Unread, the folder known so far stays. */
export async function readCollectionsFolder(): Promise<string> {
  if (knownFolder) return knownFolder;
  try {
    const response = await fetch("/library/inbox.json", { cache: "no-store" });
    if (!response.ok) return knownCollectionsFolder();
    knownFolder = collectionsFolderOf(await response.json());
  } catch {
    return knownCollectionsFolder();
  }
  return knownFolder;
}
