/**
 * Le nom du dossier d'un bac : son numéro, puis son titre, comme le moteur
 * nomme son lien dans Carts/ (`finder_name`, engine/radiotomate/services/media_bank.py).
 * C'est aussi le nom de son dossier Dropbox, qui l'ouvre aux dépôts.
 */
export function cartFolderName(cartId: number, title: string): string {
  const slug =
    (title || "")
      .trim()
      .replace(/[^A-Za-z0-9._-]+/g, "-")
      .replace(/^[-._]+|[-._]+$/g, "") || "cart";
  return `${cartId}-${slug}`;
}

/** Ce dossier vu du dossier de la station, et du dossier Dropbox de la station : sous Bacs/. */
export function finderRel(cartId: number, title: string): string {
  return `Bacs/${cartFolderName(cartId, title)}`;
}
