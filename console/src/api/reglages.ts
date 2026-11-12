/**
 * La page Réglages : ses parties selon le rôle, et la phrase qui ouvre la partie
 * Automate. Pur : pas de React, testable en node.
 */
import { worstTone, type Pillar, type PillarTone } from "./antenneState.ts";
import type { Role } from "./roles.ts";

export type ReglagesSectionId = "comptes" | "station" | "automate" | "mises-a-jour" | "compte";

export type ReglagesSection = {
  /** La valeur de `?onglet=` : les liens vers une partie la gardent. */
  id: ReglagesSectionId;
  label: string;
  /** Une partie de l'admin, qui règle la station pour toute l'équipe. */
  admin: boolean;
};

/** Dans l'ordre du menu : la station d'abord, puis le compte de chacun. */
const SECTIONS: readonly ReglagesSection[] = [
  { id: "comptes", label: "Comptes", admin: true },
  { id: "station", label: "Station", admin: true },
  { id: "automate", label: "Automate", admin: true },
  { id: "mises-a-jour", label: "Mises à jour", admin: true },
  { id: "compte", label: "Mon compte", admin: false },
];

/** L'admin voit toutes les parties. Les autres rôles, leur compte seulement : la page n'a pas de menu. */
export function reglagesSections(role: Role): ReglagesSection[] {
  return SECTIONS.filter((section) => role === "admin" || !section.admin);
}

export type AutomateSummary = { tone: PillarTone; title: string; detail: string };

const TO_THE_TECHNICIAN = "Si ça dure, préviens la personne qui s’occupe de la machine.";

/**
 * La phrase en tête de la partie Automate, d'après les six pastilles de santé : un
 * admin qui n'est pas technicien la lit, puis la transmet. `stale` : l'état n'a pas
 * été relu depuis trop longtemps ; `updatedAt`, l'heure du dernier relevé.
 */
export function automateSummary(pillars: Pillar[], stale: boolean, updatedAt: string | null): AutomateSummary {
  if (pillars.every((pillar) => pillar.tone === "off")) {
    return { tone: "off", title: "État indisponible", detail: `L’automate ne donne pas son état. ${TO_THE_TECHNICIAN}` };
  }
  if (stale) {
    return {
      tone: "off",
      title: updatedAt ? `Sans nouvelles depuis ${updatedAt}` : "Sans nouvelles",
      detail: `L’état de l’antenne n’a pas été relu depuis plus de 20 s. ${TO_THE_TECHNICIAN}`,
    };
  }
  const tone = worstTone(pillars);
  if (tone === "ok" || tone === "off") {
    return { tone: "ok", title: "Tout va bien", detail: "L’antenne tourne, sans incident ouvert." };
  }
  const causes = pillars
    .filter((pillar) => pillar.tone === tone)
    .map((pillar) => `${pillar.label} : ${pillar.value}`)
    .join(" · ");
  if (tone === "warn") return { tone, title: "À surveiller", detail: `${causes}.` };
  return {
    tone,
    title: "Problème en cours",
    detail: `${causes}. Transmets ce résumé à la personne qui s’occupe de la machine.`,
  };
}
