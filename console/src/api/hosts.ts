/**
 * Les comptes qu'on peut nommer animateur d'une émission ou d'un direct daté.
 * Pur : pas de React, testable en node.
 */
import { listedAsHost } from "./roles.ts";
import type { User } from "./types";

export const HOSTS_OUTDATED = "Mets à jour le moteur pour choisir l’animateur ici. En attendant, un admin le choisit.";
export const HOSTS_DOWN = "La liste des comptes ne répond pas. Rouvre la fenêtre pour réessayer.";
export const HOSTS_SESSION = "Session expirée : recharge la page et reconnecte-toi.";

/** Un moteur plus ancien ne donne que la liste complète des comptes, à un admin : on y garde les animateurs. */
export function hostNamesFromUsers(users: readonly User[]): string[] {
  return users.filter((user) => listedAsHost(user.permissions)).map((user) => user.username);
}

/** Les choix du champ : les comptes, plus l'animateur déjà nommé, triés à la française. */
export function hostChoices(names: readonly string[], current = ""): string[] {
  const all = new Set(names);
  const named = current.trim();
  if (named) all.add(named);
  return [...all].sort((a, b) => a.localeCompare(b, "fr"));
}
