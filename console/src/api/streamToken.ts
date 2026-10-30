/**
 * Le jeton d'encodeur : ce que l'encodeur envoie comme mot de passe au harbor, à la
 * place du mot de passe du compte. Pur : pas de React, testable en node.
 */
import { dayLongLabel, hhmm, parisWall } from "./agendaView.ts";

/** `me` : le compte connecté. Un identifiant : un autre compte, pour un admin. */
export type StreamTokenOwner = "me" | number;

/** « Jeton créé le vendredi 30 octobre à 14:05. », à l'heure de Paris. */
export function streamTokenLine(createdAt: string | null): string {
  if (!createdAt) return "Pas encore de jeton.";
  const wall = parisWall(createdAt);
  return `Jeton créé le ${dayLongLabel(wall.day)} à ${hhmm(wall.minute)}.`;
}

/** Le bouton : créer le premier jeton, en renouveler un, ou confirmer le renouvellement. */
export function streamTokenAction(createdAt: string | null, confirming: boolean): string {
  if (!createdAt) return "Créer un jeton";
  return confirming ? "Renouveler quand même" : "Renouveler";
}
