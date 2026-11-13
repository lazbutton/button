/**
 * À retirer. Les noms des dossiers de la banque, pour un moteur ou un catalogue d'avant
 * l'ADR 0019, qui ne disent pas encore ce qu'est un bac ou un titre : la console les
 * lisait alors dans les chemins. C'est le seul endroit de la console qui connaisse ces
 * noms (`layoutNames.test.ts` le vérifie). Il part avec l'étape 2 du rangement (ARC-08),
 * qui change ces noms sur le disque : une station qui la prend a déjà un moteur et un
 * catalogue qui disent tout.
 *
 * Chaque repli sert seulement quand le champ nouveau manque à la réponse.
 */

/** Le dossier de la rotation, tant que le catalogue n'a pas répondu. */
export const LEGACY_ROTATION_FOLDER = "10-rotation";

/** Le dossier où naît une collection, quand inbox.json ne le dit pas (`collections`). */
export const LEGACY_COLLECTIONS_FOLDER = "20-archives";

/** Les dossiers d'habillage qu'un bac peut suivre, quand /media/bank.json ne les dit pas (`habillage`). */
export const LEGACY_HABILLAGE_FOLDERS = [
  "30-habillage/jingles",
  "30-habillage/ids",
  "30-habillage/pubs",
  "30-habillage/beds",
  "30-habillage/stings",
  "30-habillage/sfx",
];

/** Un bac d'habillage, d'après son dossier, quand le moteur ne dit pas `bank_zone`. */
export function legacyIsHabillageFolder(bankFolder: string | null | undefined): boolean {
  return (bankFolder || "").startsWith("30-habillage");
}

/** Un titre de la rotation, d'après son dossier, quand le catalogue ne dit pas `zone`. */
export function legacyIsRotationFolder(folder: string | null | undefined): boolean {
  return (folder || "").startsWith(LEGACY_ROTATION_FOLDER);
}

/** Le bac d'un son à l'antenne, lu dans le chemin de son fichier, quand le moteur ne dit pas `cart_id`. */
export function legacyCartIdFromPath(path: string): number {
  const found = path.match(/\/50-carts\/(\d+)\//);
  return found ? Number(found[1]) : 0;
}

/** Les filtres de la recherche par dossier, quand le catalogue ne connaît pas `zone`. */
export const LEGACY_TAB_QUERY: Record<string, Record<string, string>> = {
  habillage: { folder: "30-habillage/beds,30-habillage/stings,30-habillage/sfx" },
  // Toutes les collections, celles créées plus tard aussi.
  archives: { top: LEGACY_COLLECTIONS_FOLDER },
};
